"""Handoff document schema: fixed sections so routing targets are enumerable."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SECTIONS = [
    "goal",
    "current_state",
    "decisions",
    "open_questions",
    "next_actions",
    "evidence_log",
]

TEXT_SECTIONS = ["goal", "current_state"]
LIST_SECTIONS = ["open_questions", "next_actions", "evidence_log"]

DECISION_ID_RE = re.compile(r"^D-\d+$")


def new_document(goal_id: str, goal_text: str) -> dict:
    return {
        "meta": {"goal_id": goal_id, "version": 0, "updated_at": None, "updated_by": "steward-init"},
        "goal": goal_text,
        "current_state": "",
        "decisions": [],
        "open_questions": [],
        "next_actions": [],
        "evidence_log": [],
    }


def validate_document(doc: dict) -> list[str]:
    errors = []
    for s in SECTIONS:
        if s not in doc:
            errors.append(f"missing section: {s}")
    if "meta" not in doc or "version" not in doc.get("meta", {}):
        errors.append("missing meta.version")
    for d in doc.get("decisions", []):
        if not DECISION_ID_RE.match(d.get("id", "")):
            errors.append(f"bad decision id: {d.get('id')}")
        if d.get("status", "active") not in ("active", "superseded"):
            errors.append(f"bad decision status: {d.get('status')}")
    return errors


@dataclass
class Proposal:
    """A proposed update submitted by a tool instead of a direct file write."""
    author_tool: str            # codex | claude | kimi | pi | external
    base_version: int           # canonical version the proposal was computed from
    section: str                # declared target section (Jev verifies)
    operation: str              # append | update
    content: object             # str for text sections; dict for a decision; str item for list sections
    summary: str                # one-line statement of intent, shown to Jev and humans
    author_ref: str | None = None  # fine-grained identity, e.g. claude:session-abc:subagent-3

    @classmethod
    def from_dict(cls, d: dict) -> "Proposal":
        missing = [k for k in ("author_tool", "base_version", "section", "operation", "content", "summary") if k not in d]
        if missing:
            raise ValueError(f"proposal missing fields: {missing}")
        if d["section"] not in SECTIONS:
            raise ValueError(f"unknown section: {d['section']}")
        if d["operation"] not in ("append", "update"):
            raise ValueError(f"unknown operation: {d['operation']}")
        known = ("author_tool", "base_version", "section", "operation", "content", "summary", "author_ref")
        return cls(**{k: d[k] for k in known if k in d})

    def to_dict(self) -> dict:
        d = {
            "author_tool": self.author_tool,
            "base_version": self.base_version,
            "section": self.section,
            "operation": self.operation,
            "content": self.content,
            "summary": self.summary,
        }
        if self.author_ref:
            d["author_ref"] = self.author_ref
        return d


def next_decision_id(doc: dict) -> str:
    nums = [int(d["id"].split("-")[1]) for d in doc["decisions"]]
    return f"D-{(max(nums) + 1) if nums else 1}"


def active_decisions(doc: dict) -> list[dict]:
    return [d for d in doc["decisions"] if d.get("status", "active") == "active"]


def render_markdown(doc: dict) -> str:
    m = doc["meta"]
    lines = [
        f"# Handoff — {m['goal_id']}",
        f"version: {m['version']} | updated: {m['updated_at']} by {m['updated_by']}",
        "",
        "## Goal",
        doc["goal"] or "(empty)",
        "",
        "## Current State",
        doc["current_state"] or "(empty)",
        "",
        "## Decisions",
    ]
    for d in doc["decisions"]:
        mark = "" if d.get("status", "active") == "active" else " [SUPERSEDED]"
        lines.append(f"- **{d['id']}**{mark} ({d.get('made_by','?')}): {d['text']}")
    if not doc["decisions"]:
        lines.append("(none)")
    for title, key in (("Open Questions", "open_questions"), ("Next Actions", "next_actions"), ("Evidence Log", "evidence_log")):
        lines += ["", f"## {title}"]
        items = doc[key]
        lines += [f"- {x}" for x in items] if items else ["(none)"]
    return "\n".join(lines) + "\n"
