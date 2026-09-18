"""Agent integration: install the bundled skill into agent skill dirs, and doctor checks."""
from __future__ import annotations

import os
import shutil
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


def doctor(live: bool = False, targets: list[str] | None = None) -> dict:
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
