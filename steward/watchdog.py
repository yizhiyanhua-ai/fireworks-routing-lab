"""Watchdog reconcile: external direct writes become anonymous proposals and re-enter routing."""
from __future__ import annotations

import json
import os
import time

from . import store
from .lock import exclusive
from .schema import LIST_SECTIONS, SECTIONS, TEXT_SECTIONS, Proposal
from .steward import Steward

def baseline(root: str) -> None:
    """Kept for CLI compatibility; baselines now derive from committed events."""


def _diff_to_proposals(old: dict, new: dict) -> list[Proposal]:
    """Mechanical section diff -> anonymous proposals. Semantics left to Jev."""
    proposals = []
    version = old["meta"]["version"]
    for sec in TEXT_SECTIONS:
        if old[sec] != new[sec]:
            proposals.append(Proposal(
                author_tool="external", base_version=version, section=sec,
                operation="update", content=new[sec],
                summary=f"External direct edit rewrote section '{sec}'",
            ))
    for sec in LIST_SECTIONS:
        added = [x for x in new[sec] if x not in old[sec]]
        for item in added:
            proposals.append(Proposal(
                author_tool="external", base_version=version, section=sec,
                operation="append", content=item,
                summary=f"External direct edit added an item to '{sec}'",
            ))
    old_decisions = {d["id"]: d for d in old["decisions"]}
    for d in new["decisions"]:
        prev = old_decisions.get(d["id"])
        if prev is None:
            proposals.append(Proposal(
                author_tool="external", base_version=version, section="decisions",
                operation="append", content={k: d[k] for k in ("id", "text") if k in d},
                summary=f"External direct edit added decision {d.get('id')}",
            ))
        elif prev["text"] != d["text"]:
            proposals.append(Proposal(
                author_tool="external", base_version=version, section="decisions",
                operation="update", content={"id": d["id"], "text": d["text"]},
                summary=f"External direct edit changed decision {d['id']}",
            ))
    return proposals


def reconcile(root: str, steward: Steward | None = None) -> dict:
    """One reconcile pass. Shares the steward lock so a revert can never
    interleave with an in-flight submit."""
    with exclusive(root):
        return _reconcile_locked(root, steward)


def _reconcile_locked(root: str, steward: Steward | None = None) -> dict:
    last_hash = store.last_committed_hash(root)
    if last_hash is None:
        return {"external_write": False, "note": "no anchored snapshot yet"}
    external_doc = store.load_canonical(root)
    if store.doc_hash(external_doc) == last_hash:
        return {"external_write": False}

    # External modification detected: diff current canonical against the last
    # committed snapshot, revert, and re-enter the changes as anonymous proposals.
    with open(os.path.join(root, store.SNAPSHOTS, f"{last_hash}.json")) as f:
        last_good = json.load(f)
    proposals = _diff_to_proposals(last_good, external_doc)

    # Revert the direct write; its content re-enters through the gate.
    store._write_canonical(root, last_good)
    store.record(root, {
        "type": "external_write_detected",
        "reverted_to": last_hash,
        "proposals_recovered": len(proposals),
    })

    results = []
    if proposals:
        s = steward or Steward(root)
        for p in proposals:
            results.append(s._submit_locked(p))  # already inside the lock
    return {"external_write": True, "recovered": len(proposals), "results": results}


def watch(root: str, interval: float = 5.0) -> None:
    s = Steward(root)
    while True:
        report = reconcile(root, s)
        if report.get("external_write"):
            print(json.dumps(report, ensure_ascii=False, indent=2))
        time.sleep(interval)
