"""Jev semantic gate: one parallel call per proposal. Jev judges; code merges."""
from __future__ import annotations

from dataclasses import dataclass, field

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

from .schema import LIST_SECTIONS, SECTIONS, TEXT_SECTIONS, Proposal, active_decisions

UPDATE_KINDS = {
    "new_info": "Adds genuinely new information not already present; safe to append",
    "supersedes": "Intentionally replaces existing content with newer/better information",
    "correction": "Fixes a factual error in existing content",
    "unrelated": "Does not belong in this handoff document at all",
}

MERGE_RISK_LEVELS = [
    "Compatible: no overlap with existing content, or pure addition",
    "Overlapping: touches the same facts as existing content; a field-level choice between old and new values is needed",
    "Contradictory: states something semantically incompatible with existing content; automatic merge is unsafe",
]

SECTION_CRITERIA = {
    "goal": "The overall objective; rarely changes",
    "current_state": "Where the work stands right now",
    "decisions": "Binding choices already made (architecture, approach, scope)",
    "open_questions": "Unresolved questions",
    "next_actions": "Concrete next steps",
    "evidence_log": "Pointers to artifacts, commands run, results",
    "none": "The proposal does not fit any section",
}


@dataclass
class GateResult:
    update_kind: str
    update_kind_confidence: float
    update_kind_probs: dict
    target_section: str
    target_section_confidence: float
    merge_risk: float
    merge_risk_confidence: float
    decision_conflicts: dict = field(default_factory=dict)   # D-n -> probability of contradiction
    still_applies: float | None = None                       # only set when base is stale
    usage: dict = field(default_factory=dict)


def _section_excerpt(doc: dict, section: str) -> object:
    return doc.get(section)


def check_still_applies(client: TypeSafeClient, doc: dict, proposal: Proposal) -> float:
    """Stale-base pre-check: is a proposal computed from an old version still valid now?"""
    resp = client.system_one(
        state={
            "current_document": {s: _section_excerpt(doc, s) for s in SECTIONS},
            "stale_proposal": proposal.to_dict(),
        },
        questions={
            "still_applies": Noul(
                instructions=(
                    "The proposal was written against an older version of this handoff document. "
                    "Given the document's CURRENT content, is the proposal's change still valid and applicable, "
                    "or has it been overtaken by events (already done, no longer true, or based on facts that changed)?"
                )
            )
        },
    )
    return resp.nouls["still_applies"].noul


def gate(client: TypeSafeClient, doc: dict, proposal: Proposal) -> GateResult:
    overlaps = active_decisions(doc) if proposal.section == "decisions" else []
    state = {
        "handoff_goal": doc["goal"],
        "current_section_content": _section_excerpt(doc, proposal.section),
        "active_decisions": [{"id": d["id"], "text": d["text"]} for d in active_decisions(doc)],
        "proposal": proposal.to_dict(),
    }
    questions = {
        "update_kind": Choice(
            instructions="What kind of update is this proposal, relative to the current handoff content?",
            criteria=UPDATE_KINDS,
        ),
        "target_section": Choice(
            instructions="Which section of the handoff document does this proposal actually belong to?",
            criteria=SECTION_CRITERIA,
        ),
        "merge_risk": Score(
            instructions="How risky is merging this proposal into the current handoff content?",
            criteria=MERGE_RISK_LEVELS,
        ),
    }
    # speculative fan-out: one Noul per overlapping active decision
    for d in overlaps:
        questions[f"conflict_{d['id']}"] = Noul(
            instructions=(
                f"Does the proposal contradict or reverse the existing recorded decision {d['id']}: "
                f"\"{d['text']}\"? Answer yes only for a genuine semantic contradiction, "
                "not for adding detail or an unrelated new decision."
            )
        )

    resp = client.system_one(state=state, questions=questions)
    result = GateResult(
        update_kind=resp.choices["update_kind"].choice,
        update_kind_confidence=resp.choices["update_kind"].confidence,
        update_kind_probs=dict(resp.choices["update_kind"].probabilities),
        target_section=resp.choices["target_section"].choice,
        target_section_confidence=resp.choices["target_section"].confidence,
        merge_risk=resp.scores["merge_risk"].score,
        merge_risk_confidence=resp.scores["merge_risk"].confidence,
        decision_conflicts={
            d["id"]: resp.nouls[f"conflict_{d['id']}"].noul for d in overlaps
        },
    )
    if hasattr(resp, "usage") and resp.usage is not None:
        result.usage = dict(resp.usage) if not isinstance(resp.usage, dict) else resp.usage
    return result


def select_value(client: TypeSafeClient, doc: dict, proposal: Proposal) -> tuple[str, float]:
    """Field-level selection for merge_risk level 1: pick a candidate, never generate."""
    resp = client.system_one(
        state={
            "section": proposal.section,
            "existing_content": _section_excerpt(doc, proposal.section),
            "proposed_change": proposal.to_dict(),
        },
        questions={
            "resolution": Choice(
                instructions=(
                    "The proposed change overlaps existing content. Which resolution is correct? "
                    "Judge by which preserves more accurate, current information for the handoff's goal."
                ),
                criteria={
                    "accept_proposed": "The proposed value is more accurate/current; replace the old one",
                    "keep_existing": "The existing content is more accurate/current; discard the proposal",
                    "needs_human": "Both contain important conflicting information; a person must decide",
                },
            )
        },
    )
    c = resp.choices["resolution"]
    return c.choice, c.confidence
