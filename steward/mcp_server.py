"""MCP server: expose the steward as native tools for coding agents.

One implementation serves every MCP-capable agent (Claude Code, Codex, Cursor,
Gemini, Kimi). Run: `handoff-steward mcp` (stdio transport).

Requires the optional dependency: pip install handoff-steward[mcp]
"""
from __future__ import annotations

import json
import os

from . import store
from .schema import Proposal
from .steward import Steward


def _resolve_root(root: str | None) -> str:
    r = root or os.environ.get("HANDOFF_STORE")
    if not r:
        raise ValueError(
            "No store root given. Pass `root` or set HANDOFF_STORE. "
            "A store is a directory created by `handoff-steward --root <dir> init`."
        )
    return r


def handle_submit_proposal(proposal: dict, root: str | None = None) -> dict:
    return Steward(_resolve_root(root)).submit(Proposal.from_dict(proposal))


def handle_get_status(root: str | None = None) -> dict:
    doc = store.load_canonical(_resolve_root(root))
    return {
        "version": doc["meta"]["version"],
        "updated_at": doc["meta"]["updated_at"],
        "updated_by": doc["meta"]["updated_by"],
        "goal": doc["goal"],
        "active_decisions": [
            {"id": d["id"], "text": d["text"]}
            for d in doc["decisions"] if d.get("status", "active") == "active"
        ],
        "open_questions": doc["open_questions"],
        "next_actions": doc["next_actions"],
        "pending_escalations": len(list_escalations_sync(_resolve_root(root))),
    }


def handle_get_history(root: str | None = None, limit: int = 50) -> list[dict]:
    return store.history(_resolve_root(root))[-limit:]


def list_escalations_sync(root: str) -> list[str]:
    esc_dir = os.path.join(root, store.ESCALATIONS)
    if not os.path.isdir(esc_dir):
        return []
    return sorted(os.listdir(esc_dir))


def handle_list_escalations(root: str | None = None) -> list[dict]:
    r = _resolve_root(root)
    out = []
    for name in list_escalations_sync(r):
        with open(os.path.join(r, store.ESCALATIONS, name)) as f:
            out.append(json.load(f))
    return out


def handle_init_store(root: str, goal_id: str, goal: str) -> dict:
    doc = store.init_store(root, goal_id, goal)
    return {"initialized": True, "root": root, "version": doc["meta"]["version"]}


def create_server():
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("handoff-steward")

    @mcp.tool()
    def submit_proposal(proposal: dict, root: str | None = None) -> dict:
        """Submit a handoff update proposal. The Jev gate routes it:
        auto_commit / field_select / escalate / reject. Never write the
        handoff files directly — always go through this tool."""
        return handle_submit_proposal(proposal, root)

    @mcp.tool()
    def get_status(root: str | None = None) -> dict:
        """Current version, active decisions, open questions, pending escalations."""
        return handle_get_status(root)

    @mcp.tool()
    def get_history(root: str | None = None, limit: int = 50) -> list[dict]:
        """Append-only event log: every commit, reject, escalation, external write."""
        return handle_get_history(root, limit)

    @mcp.tool()
    def list_escalations(root: str | None = None) -> list[dict]:
        """Escalation briefs waiting for a human ruling."""
        return handle_list_escalations(root)

    @mcp.tool()
    def init_store(root: str, goal_id: str, goal: str) -> dict:
        """Initialize a new versioned handoff store for a goal."""
        return handle_init_store(root, goal_id, goal)

    return mcp


def main() -> None:
    try:
        server = create_server()
    except ImportError:
        raise SystemExit(
            "MCP support requires the optional dependency: pip install handoff-steward[mcp]"
        )
    server.run()
