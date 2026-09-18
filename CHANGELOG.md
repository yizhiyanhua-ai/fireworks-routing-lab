# Changelog

## [0.1.0] - 2026-09-18

First public release.

### Added
- **Steward core**: single-writer gateway for handoff documents; proposals instead of direct writes
- **Jev semantic gate** (TypeSafe System One): one parallel call judges `update_kind`, `target_section`, `decision_conflict` (fan-out), `merge_risk`; `still_applies` pre-check for stale bases
- **Routing table**: auto_commit / field_select / escalate / reject with configurable thresholds (`config.json`)
- **Versioned store**: append-only `events.jsonl`, content-addressed snapshots, atomic canonical writes, `handoff.md` projection
- **Inter-process serialization**: flock-based mutex shared by `submit` and `reconcile` — safe for concurrent sessions/subagents
- **Watchdog reconcile**: external direct writes are detected, reverted, and re-entered as anonymous proposals
- **Fail-closed degradation**: Jev/API failures escalate to a human; nothing is auto-committed or silently dropped
- **CLI**: `init`, `submit`, `status`, `history`, `reconcile`, `watch`
- **Tests**: offline unit tests (pytest), live routing matrix (10 cases), live concurrency test (6 parallel processes)
