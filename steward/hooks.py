"""Agent hook handlers: guard (PreToolUse), session-start, subagent-stop, file-changed.

These are plain commands that read hook JSON from stdin and print hook JSON on
stdout, so any agent with a hook system (Claude Code, Cursor, ...) can wire them.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import store as store_mod

STORE_MARKER_FILES = ("canonical.json", "events.jsonl")
MAX_ANCESTOR_HOPS = 5


def find_store_root(path: str) -> str | None:
    """A directory is a steward store iff it contains canonical.json + events.jsonl."""
    p = Path(path).resolve()
    if p.suffix:  # a file path: start from its parent
        p = p.parent
    for _ in range(MAX_ANCESTOR_HOPS):
        if all((p / m).exists() for m in STORE_MARKER_FILES):
            return str(p)
        if p.parent == p:
            break
        p = p.parent
    return None


def _extract_file_path(payload: dict) -> str | None:
    ti = payload.get("tool_input") or {}
    return ti.get("file_path") or ti.get("path")


def guard(payload: dict) -> dict | None:
    """PreToolUse: deny direct writes into any steward store."""
    file_path = _extract_file_path(payload)
    if not file_path:
        return None
    root = find_store_root(file_path)
    if not root:
        return None
    name = os.path.basename(file_path)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"'{name}' lives in a handoff-steward store ({root}). Direct writes are "
                "reverted by the watchdog. Submit a proposal instead: "
                f"handoff-steward --root {root} submit --proposal <file.json> "
                "or the submit_proposal MCP tool."
            ),
        }
    }


def _scan_stores(cwd: str) -> list[str]:
    """Stores in cwd ancestors plus conventional <cwd>/.handoff/* locations."""
    found = []
    probe = find_store_root(cwd)
    if probe:
        found.append(probe)
    handoff_dir = Path(cwd) / ".handoff"
    if handoff_dir.is_dir():
        for child in sorted(handoff_dir.iterdir()):
            if child.is_dir() and find_store_root(str(child)) and str(child) not in found:
                found.append(str(child))
    return found


def _store_summary(root: str) -> str:
    doc = store_mod.load_canonical(root)
    esc_dir = Path(root) / store_mod.ESCALATIONS
    pending = len(list(esc_dir.iterdir())) if esc_dir.is_dir() else 0
    active = [d for d in doc["decisions"] if d.get("status", "active") == "active"]
    return (
        f"- {root}: v{doc['meta']['version']}, {len(active)} active decisions, "
        f"{pending} pending escalations"
    )


def session_start(payload: dict) -> dict | None:
    """SessionStart: inject store state so the agent knows before asking."""
    cwd = payload.get("cwd") or os.getcwd()
    stores = _scan_stores(cwd)
    lines = [
        "handoff-steward is active. Never write canonical.json/handoff.md directly; "
        "submit proposals via `handoff-steward submit` or the submit_proposal MCP tool.",
    ]
    if stores:
        lines.append("Stores in scope:")
        lines += [_store_summary(s) for s in stores]
        if any("pending escalations: 0" not in _store_summary(s) for s in stores):
            lines.append("Pending escalations need a human ruling before conflicting work proceeds.")
    return {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(lines),
        }
    }


def subagent_stop(payload: dict) -> dict | None:
    """SubagentStop: remind that findings must go through the steward."""
    cwd = payload.get("cwd") or os.getcwd()
    stores = _scan_stores(cwd)
    if not stores:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStop",
            "additionalContext": (
                "If this subagent produced decisions, evidence, or state relevant to the "
                "shared handoff, make sure they were submitted via handoff-steward "
                "(submit_proposal), each with its own author_ref."
            ),
        }
    }


def file_changed(payload: dict) -> dict | None:
    """Post-write reconcile trigger (e.g. Cursor afterFileEdit): if the changed file
    is inside a store, run one reconcile pass and report what happened."""
    file_path = _extract_file_path(payload)
    if not file_path:
        return None
    root = find_store_root(file_path)
    if not root:
        return None
    from . import watchdog
    report = watchdog.reconcile(root)
    if not report.get("external_write"):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (
                f"handoff-steward watchdog reverted a direct write in {root} and "
                f"re-routed {report.get('recovered', 0)} recovered proposal(s) through the Jev gate."
            ),
        }
    }


HANDLERS = {
    "guard": guard,
    "session-start": session_start,
    "subagent-stop": subagent_stop,
    "file-changed": file_changed,
}


def run_hook(name: str) -> None:
    """CLI entry: read hook payload JSON from stdin, write decision JSON to stdout."""
    handler = HANDLERS[name]
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except json.JSONDecodeError:
        payload = {}
    result = handler(payload)
    if result is not None:
        json.dump(result, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")


# ---------- install ----------

CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
CURSOR_HOOKS = Path.home() / ".cursor" / "hooks.json"

_CLAUDE_HOOKS = {
    "PreToolUse": [{"matcher": "Write|Edit|NotebookEdit",
                    "hooks": [{"type": "command", "command": "handoff-steward hook guard"}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "handoff-steward hook session-start"}]}],
    "SubagentStop": [{"hooks": [{"type": "command", "command": "handoff-steward hook subagent-stop"}]}],
}

_CURSOR_HOOKS = {"afterFileEdit": [{"command": "handoff-steward hook file-changed"}]}


def _merge_hook_list(existing: list, additions: list, key) -> tuple[list, bool]:
    changed = False
    seen = {key(h) for h in existing}
    for h in additions:
        if key(h) not in seen:
            existing.append(h)
            changed = True
    return existing, changed


def install_hooks(agent: str, settings_path: Path | None = None) -> str:
    if agent == "claude":
        path = settings_path or CLAUDE_SETTINGS
        data = json.loads(path.read_text()) if path.exists() else {}
        hooks = data.setdefault("hooks", {})
        changed = False
        for event, entries in _CLAUDE_HOOKS.items():
            merged, c = _merge_hook_list(hooks.get(event, []), entries,
                                         lambda e: json.dumps(e, sort_keys=True))
            hooks[event] = merged
            changed = changed or c
        if changed or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            return "installed"
        return "already installed"
    if agent == "cursor":
        path = settings_path or CURSOR_HOOKS
        data = json.loads(path.read_text()) if path.exists() else {"version": 1, "hooks": {}}
        hooks = data.setdefault("hooks", {})
        changed = False
        for event, entries in _CURSOR_HOOKS.items():
            merged, c = _merge_hook_list(hooks.get(event, []), entries,
                                         lambda e: json.dumps(e, sort_keys=True))
            hooks[event] = merged
            changed = changed or c
        if changed or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            return "installed"
        return "already installed"
    return f"skipped: hooks not supported for '{agent}'"
