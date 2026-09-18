"""Routing table: turn GateResult into a Verdict. Policy lives here, explicit and configurable."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .jev_gate import GateResult
from .schema import Proposal

DEFAULT_CONFIG = {
    "confidence_floor": 0.5,        # below this on any decisive answer -> escalate
    "conflict_probability": 0.6,    # decision_conflict Noul above this -> conflict path
    "still_applies_floor": 0.5,     # stale proposal below this -> reject as stale
    "auto_commit_max_risk": 0.5,    # merge_risk score at/below this -> auto commit
    "field_select_max_risk": 1.5,   # above this (level 2 leaning) -> escalate
    "field_select_min_confidence": 0.6,
}


def load_config(root: str) -> dict:
    path = os.path.join(root, "config.json")
    if os.path.exists(path):
        with open(path) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)


@dataclass
class Verdict:
    action: str           # auto_commit | field_select | escalate | reject
    reason: str
    gate: GateResult | None = None


def route(gate: GateResult, proposal: Proposal, config: dict) -> Verdict:
    floor = config["confidence_floor"]

    if gate.update_kind == "unrelated":
        return Verdict("reject", "Jev: update_kind=unrelated", gate)

    if gate.still_applies is not None and gate.still_applies < config["still_applies_floor"]:
        return Verdict(
            "reject",
            f"stale base and still_applies={gate.still_applies:.2f} < {config['still_applies_floor']}",
            gate,
        )

    conflicts = {k: v for k, v in gate.decision_conflicts.items() if v > config["conflict_probability"]}
    if conflicts:
        return Verdict(
            "escalate",
            f"decision conflict: {', '.join(f'{k} p={v:.2f}' for k, v in conflicts.items())}",
            gate,
        )

    if gate.update_kind_confidence < floor or gate.merge_risk_confidence < floor:
        return Verdict(
            "escalate",
            f"low confidence: update_kind={gate.update_kind_confidence:.2f}, "
            f"merge_risk={gate.merge_risk_confidence:.2f} (floor {floor})",
            gate,
        )

    if gate.merge_risk <= config["auto_commit_max_risk"]:
        return Verdict("auto_commit", f"merge_risk={gate.merge_risk:.2f} compatible", gate)

    if gate.merge_risk <= config["field_select_max_risk"]:
        return Verdict("field_select", f"merge_risk={gate.merge_risk:.2f} needs field-level choice", gate)

    return Verdict("escalate", f"merge_risk={gate.merge_risk:.2f} contradictory", gate)
