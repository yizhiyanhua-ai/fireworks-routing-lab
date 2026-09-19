"""Agent integration: install the bundled skill into agent skill dirs, and doctor checks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ASSET_DIR = Path(__file__).parent / "assets" / "handoff-steward"
SKILL_NAME = "handoff-steward"

# Well-known agent skill directories (created by the respective tools).
AGENT_SKILL_DIRS = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".agents" / "skills",
    Path.home() / ".pi" / "agent" / "skills",
]


def install_skill(targets: list[str] | None = None, create: bool = False) -> list[dict]:
    """Copy the bundled SKILL.md into each detected (or given) agent skill dir.

    Returns a per-target report. Existing installations are overwritten only if the
    bundled version differs.
    """
    results = []
    dirs = [Path(t).expanduser() for t in targets] if targets else AGENT_SKILL_DIRS
    for d in dirs:
        dest = d / SKILL_NAME
        entry = {"target": str(dest), "status": None}
        if not d.exists():
            if targets or create:
                d.mkdir(parents=True, exist_ok=True)
            else:
                entry["status"] = "skipped: dir does not exist"
                results.append(entry)
                continue
        src_md = (ASSET_DIR / "SKILL.md").read_text()
        dest_md = dest / "SKILL.md"
        existed_before = dest_md.exists()
        if existed_before and dest_md.read_text() == src_md:
            entry["status"] = "already up to date"
        else:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(ASSET_DIR, dest)
            entry["status"] = "updated" if existed_before else "installed"
        results.append(entry)
    return results


# ---------- MCP registration ----------

MCP_SERVER_NAME = "handoff-steward"
MCP_COMMAND = "handoff-steward-mcp"
MCP_JSON_TARGETS = {
    "cursor": Path.home() / ".cursor" / "mcp.json",
    "gemini": Path.home() / ".gemini" / "settings.json",
    "kimi": Path.home() / ".kimi-code" / "mcp.json",
}
CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
CLAUDE_JSON = Path.home() / ".claude.json"


def _mcp_registered_in_json(path: Path) -> bool:
    try:
        data = json.loads(path.read_text())
        return MCP_SERVER_NAME in data.get("mcpServers", {})
    except Exception:
        return False


def _register_json(path: Path, create: bool) -> str:
    if _mcp_registered_in_json(path):
        return "already registered"
    if not path.exists() and not create:
        return "skipped: config does not exist"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault("mcpServers", {})[MCP_SERVER_NAME] = {"command": MCP_COMMAND}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return "registered"


def _codex_registered() -> bool:
    try:
        return f"mcp_servers.{MCP_SERVER_NAME}" in CODEX_CONFIG.read_text()
    except Exception:
        return False


def _register_codex(create: bool) -> str:
    if _codex_registered():
        return "already registered"
    if not CODEX_CONFIG.exists() and not create:
        return "skipped: config does not exist"
    CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with CODEX_CONFIG.open("a") as f:
        f.write(f"\n[mcp_servers.{MCP_SERVER_NAME}]\ncommand = \"{MCP_COMMAND}\"\n")
    return "registered"


def _register_claude() -> str:
    if shutil.which("claude"):
        subprocess.run(
            ["claude", "mcp", "add", MCP_SERVER_NAME, "--", MCP_COMMAND],
            check=True, capture_output=True,
        )
        return "registered via claude mcp add"
    return _register_json(CLAUDE_JSON, create=True)


def install_mcp(agents: list[str] | None = None, create: bool = True) -> list[dict]:
    """Register the MCP server with coding agents."""
    wanted = agents or ["claude", "codex", "cursor", "gemini", "kimi"]
    results = []
    for agent in wanted:
        entry = {"agent": agent}
        try:
            if agent == "claude":
                entry["status"] = _register_claude()
            elif agent == "codex":
                entry["status"] = _register_codex(create)
            elif agent in MCP_JSON_TARGETS:
                entry["status"] = _register_json(MCP_JSON_TARGETS[agent], create)
            else:
                entry["status"] = f"skipped: unknown agent '{agent}'"
        except Exception as exc:
            entry["status"] = f"error: {type(exc).__name__}: {exc}"
        results.append(entry)
    return results


def mcp_registrations() -> dict[str, bool]:
    """Used by doctor: is the MCP server registered for each agent?"""
    return {
        "claude": _mcp_registered_in_json(CLAUDE_JSON),
        "codex": _codex_registered(),
        "cursor": _mcp_registered_in_json(MCP_JSON_TARGETS["cursor"]),
        "gemini": _mcp_registered_in_json(MCP_JSON_TARGETS["gemini"]),
        "kimi": _mcp_registered_in_json(MCP_JSON_TARGETS["kimi"]),
    }


def doctor(live: bool = False, targets: list[str] | None = None, mcp: bool = False) -> dict:
    """Check environment readiness. Exits nonzero via CLI when required checks fail."""
    checks = []

    key = os.environ.get("TYPESAFE_API_KEY", "")
    checks.append({
        "name": "TYPESAFE_API_KEY",
        "ok": bool(key),
        "detail": f"set (len={len(key)})" if key else "missing — create one at https://console.typesafe.ai/settings/keys",
        "required": True,
    })

    dirs = [Path(t).expanduser() for t in targets] if targets else AGENT_SKILL_DIRS
    found_any = False
    for d in dirs:
        installed = (d / SKILL_NAME / "SKILL.md").exists()
        found_any = found_any or installed
        checks.append({
            "name": f"skill in {d}",
            "ok": installed,
            "detail": "installed" if installed else "not installed (run: handoff-steward install-skill)",
            "required": False,
        })
    checks.append({
        "name": "skill installed in >= 1 agent dir",
        "ok": found_any,
        "detail": "ok" if found_any else "no agent will discover the write-gateway contract",
        "required": True,
    })

    if mcp:
        regs = mcp_registrations()
        for agent, registered in regs.items():
            checks.append({
                "name": f"mcp registered: {agent}",
                "ok": registered,
                "detail": "registered" if registered else "not registered (run: handoff-steward install-mcp)",
                "required": False,
            })
        checks.append({
            "name": "mcp registered for >= 1 agent",
            "ok": any(regs.values()),
            "detail": "ok" if any(regs.values()) else "run: handoff-steward install-mcp",
            "required": False,
        })

    if live:
        try:
            from typesafe_sdk import Noul, TypeSafeClient
            with TypeSafeClient() as client:
                client.system_one(state="ping", questions={"ok": Noul(instructions="Is this a connectivity check?")})
            checks.append({"name": "live API ping", "ok": True, "detail": "Jev reachable", "required": True})
        except Exception as exc:
            checks.append({"name": "live API ping", "ok": False,
                           "detail": f"{type(exc).__name__}: {exc}", "required": True})

    ok = all(c["ok"] for c in checks if c["required"])
    return {"ok": ok, "checks": checks}
