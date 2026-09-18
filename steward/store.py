"""Append-only event log + content-addressed snapshots. Canonical doc is a projection."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone

from .schema import new_document, render_markdown, validate_document

CANONICAL = "canonical.json"
MARKDOWN = "handoff.md"
EVENTS = "events.jsonl"
SNAPSHOTS = "snapshots"
ESCALATIONS = "escalations"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_store(root: str, goal_id: str, goal_text: str) -> dict:
    os.makedirs(os.path.join(root, SNAPSHOTS), exist_ok=True)
    os.makedirs(os.path.join(root, ESCALATIONS), exist_ok=True)
    if os.path.exists(os.path.join(root, CANONICAL)):
        raise FileExistsError(f"store already initialized at {root}")
    doc = new_document(goal_id, goal_text)
    h = doc_hash(doc)
    with open(os.path.join(root, SNAPSHOTS, f"{h}.json"), "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    _append_event(root, {"type": "init", "goal_id": goal_id, "ts": _now(), "doc_hash": h})
    _write_canonical(root, doc)
    return doc


def load_canonical(root: str) -> dict:
    with open(os.path.join(root, CANONICAL)) as f:
        return json.load(f)


def canonical_hash(root: str) -> str:
    with open(os.path.join(root, CANONICAL), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def doc_hash(doc: dict) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def last_committed_hash(root: str) -> str | None:
    """doc_hash of the newest snapshot-anchored event (init or commit)."""
    anchored = [e for e in history(root) if e.get("doc_hash")]
    return anchored[-1]["doc_hash"] if anchored else None


def commit(root: str, doc: dict, event: dict) -> dict:
    """Bump version, persist snapshot + canonical + markdown projection, append event."""
    errors = validate_document(doc)
    if errors:
        raise ValueError(f"invalid document: {errors}")
    doc["meta"]["version"] += 1
    doc["meta"]["updated_at"] = _now()
    h = doc_hash(doc)
    event = {**event, "ts": _now(), "new_version": doc["meta"]["version"], "doc_hash": h}
    with open(os.path.join(root, SNAPSHOTS, f"{h}.json"), "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    _write_canonical(root, doc)
    _append_event(root, event)
    return doc


def record(root: str, event: dict) -> None:
    """Append a non-commit event (reject/escalation) without touching canonical."""
    _append_event(root, {**event, "ts": _now()})


def write_escalation(root: str, brief: dict) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(root, ESCALATIONS, f"esc-{ts}-{brief.get('author_tool','unknown')}.json")
    with open(path, "w") as f:
        json.dump({**brief, "ts": _now()}, f, ensure_ascii=False, indent=2)
    return path


def history(root: str) -> list[dict]:
    path = os.path.join(root, EVENTS)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_canonical(root: str, doc: dict) -> None:
    # atomic write: tmp + rename
    fd, tmp = tempfile.mkstemp(dir=root, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(root, CANONICAL))
    with open(os.path.join(root, MARKDOWN), "w") as f:
        f.write(render_markdown(doc))


def _append_event(root: str, event: dict) -> None:
    with open(os.path.join(root, EVENTS), "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
