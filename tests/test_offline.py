"""Offline unit tests — no API key, no network. Run: pytest tests/test_offline.py"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steward import store
from steward.jev_gate import GateResult
from steward.router import DEFAULT_CONFIG, route
from steward.schema import Proposal, new_document, next_decision_id, render_markdown, validate_document
from steward.steward import apply_proposal
from steward.watchdog import _diff_to_proposals


@pytest.fixture()
def root(tmp_path):
    return str(tmp_path / "store")


def make_proposal(**kw):
    base = dict(author_tool="codex", base_version=0, section="next_actions",
                operation="append", content="do X", summary="add action")
    return Proposal(**{**base, **kw})


def make_gate(**kw):
    base = dict(update_kind="new_info", update_kind_confidence=0.9, update_kind_probs={},
                target_section="next_actions", target_section_confidence=0.9,
                merge_risk=0.1, merge_risk_confidence=0.9, decision_conflicts={})
    return GateResult(**{**base, **kw})


# ---- schema ----

def test_new_document_valid():
    assert validate_document(new_document("g", "goal text")) == []


def test_proposal_roundtrip_and_author_ref():
    p = make_proposal(author_ref="claude:session-1:subagent-2")
    assert Proposal.from_dict(p.to_dict()).author_ref == "claude:session-1:subagent-2"
    assert "author_ref" not in make_proposal().to_dict()


def test_proposal_rejects_unknown_section():
    with pytest.raises(ValueError):
        Proposal.from_dict({**make_proposal().to_dict(), "section": "nonsense"})


def test_decision_id_sequence():
    doc = new_document("g", "x")
    assert next_decision_id(doc) == "D-1"
    doc["decisions"].append({"id": "D-1", "text": "t", "made_by": "a", "status": "active"})
    assert next_decision_id(doc) == "D-2"


# ---- store ----

def test_store_init_commit_history(root):
    store.init_store(root, "g", "goal")
    doc = store.load_canonical(root)
    new = apply_proposal(doc, make_proposal())
    store.commit(root, new, {"type": "commit", "proposal": {}})
    assert store.load_canonical(root)["meta"]["version"] == 1
    assert store.last_committed_hash(root) is not None
    assert any(e["type"] == "init" for e in store.history(root))
    assert os.path.exists(os.path.join(root, "handoff.md"))


def test_render_markdown_contains_sections(root):
    store.init_store(root, "g", "goal")
    md = render_markdown(store.load_canonical(root))
    for heading in ("## Goal", "## Decisions", "## Next Actions"):
        assert heading in md


# ---- apply_proposal ----

def test_apply_decision_update_supersedes():
    doc = new_document("g", "x")
    doc = apply_proposal(doc, make_proposal(section="decisions",
                                            content={"text": "use Postgres"}))
    assert doc["decisions"][0]["id"] == "D-1"
    doc = apply_proposal(doc, make_proposal(section="decisions", operation="update",
                                            content={"id": "D-1", "text": "use SQLite"}))
    statuses = {d["text"]: d["status"] for d in doc["decisions"]}
    assert statuses["use Postgres"] == "superseded"
    assert statuses["use SQLite"] == "active"


# ---- router ----

def test_route_table():
    cfg = dict(DEFAULT_CONFIG)
    assert route(make_gate(), make_proposal(), cfg).action == "auto_commit"
    assert route(make_gate(update_kind="unrelated"), make_proposal(), cfg).action == "reject"
    assert route(make_gate(decision_conflicts={"D-1": 0.9}), make_proposal(section="decisions"), cfg).action == "escalate"
    assert route(make_gate(merge_risk=1.0), make_proposal(), cfg).action == "field_select"
    assert route(make_gate(merge_risk=2.0), make_proposal(), cfg).action == "escalate"
    assert route(make_gate(update_kind_confidence=0.3), make_proposal(), cfg).action == "escalate"
    assert route(make_gate(still_applies=0.2), make_proposal(), cfg).action == "reject"


# ---- watchdog diff ----

def test_diff_to_proposals_detects_changes(root):
    store.init_store(root, "g", "goal")
    old = store.load_canonical(root)
    new = {**old, "current_state": "externally rewritten",
           "open_questions": ["injected question"],
           "decisions": [{"id": "D-1", "text": "sneaky", "made_by": "x", "status": "active"}]}
    proposals = _diff_to_proposals(old, new)
    kinds = {(p.section, p.operation) for p in proposals}
    assert ("current_state", "update") in kinds
    assert ("open_questions", "append") in kinds
    assert ("decisions", "append") in kinds
    assert all(p.author_tool == "external" for p in proposals)


# ---- install & doctor ----

def test_install_skill_lifecycle(tmp_path):
    from steward.install import doctor, install_skill
    target = tmp_path / "skills"
    results = install_skill(targets=[str(target)])
    assert results[0]["status"] == "installed"
    assert (target / "handoff-steward" / "SKILL.md").exists()
    assert install_skill(targets=[str(target)])[0]["status"] == "already up to date"
    (target / "handoff-steward" / "SKILL.md").write_text("stale")
    assert install_skill(targets=[str(target)])[0]["status"] == "updated"


def test_doctor_reports_missing_key_and_skill(tmp_path, monkeypatch):
    from steward.install import doctor
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    report = doctor(targets=[str(tmp_path / "nowhere")])
    assert report["ok"] is False
    by_name = {c["name"]: c for c in report["checks"]}
    assert by_name["TYPESAFE_API_KEY"]["ok"] is False
    monkeypatch.setenv("TYPESAFE_API_KEY", "k")
    assert doctor(targets=[str(tmp_path / "nowhere")])["ok"] is False  # skill still missing


# ---- fail-closed ----

def test_submit_fails_closed_when_jev_down(root):
    """A client that always raises must produce an escalation, never a commit."""
    class BrokenClient:
        def system_one(self, **kw):
            raise ConnectionError("jev unreachable")
        def close(self):
            pass

    from steward.steward import Steward
    store.init_store(root, "g", "goal")
    result = Steward(root, client=BrokenClient()).submit(make_proposal())
    assert result["action"] == "escalate"
    assert "jev_unavailable" in result["reason"]
    assert store.load_canonical(root)["meta"]["version"] == 0  # nothing committed
    assert os.listdir(os.path.join(root, "escalations"))        # brief written
