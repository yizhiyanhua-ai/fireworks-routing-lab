"""Steward: single-writer gateway. submit() serializes all handoff mutations."""
from __future__ import annotations

import copy

from typesafe_sdk import TypeSafeClient

from . import jev_gate, store
from .lock import exclusive
from .router import Verdict, load_config, route
from .schema import LIST_SECTIONS, TEXT_SECTIONS, Proposal, next_decision_id


def apply_proposal(doc: dict, proposal: Proposal) -> dict:
    """Deterministic merge mechanics. Only called after routing approves."""
    new = copy.deepcopy(doc)
    sec, op, content = proposal.section, proposal.operation, proposal.content
    if sec in TEXT_SECTIONS:
        new[sec] = content if op == "update" else (new[sec] + "\n" + content).strip()
    elif sec == "decisions":
        if op == "append":
            entry = dict(content)
            entry.setdefault("id", next_decision_id(new))
            entry.setdefault("made_by", proposal.author_tool)
            entry.setdefault("status", "active")
            new["decisions"].append(entry)
        else:  # update: supersede existing decision by id
            target = content["id"]
            for d in new["decisions"]:
                if d["id"] == target:
                    d["status"] = "superseded"
            entry = {"id": target, "text": content["text"], "made_by": proposal.author_tool, "status": "active"}
            new["decisions"].append(entry)
    elif sec in LIST_SECTIONS:
        if op == "append":
            new[sec].append(content)
        else:  # update: replace matching item
            old = content.get("old")
            new[sec] = [content["new"] if x == old else x for x in new[sec]]
    return new


class Steward:
    def __init__(self, root: str, client: TypeSafeClient | None = None):
        self.root = root
        self.config = load_config(root)
        self._client = client

    def submit(self, proposal: Proposal) -> dict:
        # Exclusive lock: this is the serialized queue. Concurrent sessions and
        # subagents (same tool or different tools) line up here.
        with exclusive(self.root):
            return self._submit_locked(proposal)

    def _submit_locked(self, proposal: Proposal) -> dict:
        doc = store.load_canonical(self.root)
        stale = proposal.base_version != doc["meta"]["version"]
        client = self._client or TypeSafeClient()
        try:
            gate = jev_gate.gate(client, doc, proposal)
            if stale:
                gate.still_applies = jev_gate.check_still_applies(client, doc, proposal)
            verdict = route(gate, proposal, self.config)
            if verdict.action == "field_select":
                verdict = self._resolve_field_select(client, doc, proposal, verdict)
        except Exception as exc:
            # Fail-closed: when Jev is unreachable the proposal escalates to a
            # human. It is NEVER auto-committed and NEVER silently dropped.
            verdict = Verdict(
                "escalate",
                f"jev_unavailable: {type(exc).__name__}: {exc}",
                None,
            )
        finally:
            if self._client is None:
                client.close()
        return self._execute(doc, proposal, verdict, stale)

    def _resolve_field_select(self, client, doc, proposal, verdict: Verdict) -> Verdict:
        choice, conf = jev_gate.select_value(client, doc, proposal)
        if choice == "accept_proposed" and conf >= self.config["field_select_min_confidence"]:
            return Verdict("auto_commit", f"{verdict.reason}; field-select accept_proposed conf={conf:.2f}", verdict.gate)
        if choice == "keep_existing" and conf >= self.config["field_select_min_confidence"]:
            return Verdict("reject", f"field-select keep_existing conf={conf:.2f}; proposal discarded", verdict.gate)
        return Verdict("escalate", f"field-select inconclusive: {choice} conf={conf:.2f}", verdict.gate)

    def _execute(self, doc: dict, proposal: Proposal, verdict: Verdict, stale: bool) -> dict:
        gate = verdict.gate
        base_event = {
            "proposal": proposal.to_dict(),
            "stale_base": stale,
            "gate": _gate_dict(gate),
            "verdict": {"action": verdict.action, "reason": verdict.reason},
        }
        if verdict.action == "auto_commit":
            new_doc = apply_proposal(doc, proposal)
            new_doc["meta"]["updated_by"] = proposal.author_tool
            store.commit(self.root, new_doc, {**base_event, "type": "commit"})
        elif verdict.action == "escalate":
            path = store.write_escalation(self.root, {
                **base_event,
                "author_tool": proposal.author_tool,
                "canonical_version": doc["meta"]["version"],
            })
            store.record(self.root, {**base_event, "type": "escalation", "brief": path})
        else:  # reject
            store.record(self.root, {**base_event, "type": "reject"})
        return {
            "action": verdict.action,
            "reason": verdict.reason,
            "version": store.load_canonical(self.root)["meta"]["version"],
            "gate": _gate_dict(gate),
        }


def _gate_dict(gate) -> dict | None:
    if gate is None:
        return None
    return {
        "update_kind": gate.update_kind,
        "update_kind_confidence": round(gate.update_kind_confidence, 3),
        "target_section": gate.target_section,
        "target_section_confidence": round(gate.target_section_confidence, 3),
        "merge_risk": round(gate.merge_risk, 3),
        "merge_risk_confidence": round(gate.merge_risk_confidence, 3),
        "decision_conflicts": {k: round(v, 3) for k, v in gate.decision_conflicts.items()},
        "still_applies": None if gate.still_applies is None else round(gate.still_applies, 3),
    }
