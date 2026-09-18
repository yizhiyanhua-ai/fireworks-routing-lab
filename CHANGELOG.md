# Changelog

## [Unreleased]

### Added
- **Bundled agent skill** (`steward/assets/handoff-steward/SKILL.md`): the write-gateway
  behavioral contract, shipped inside the package — generic paths, works for any agent
- **`handoff-steward install-skill`**: auto-detects `~/.claude/skills`, `~/.codex/skills`,
  `~/.agents/skills`, `~/.pi/agent/skills` and installs/updates the skill; `--target`, `--create`
- **`handoff-steward doctor`**: verifies API key, skill installation, and (with `--live`)
  TypeSafe API reachability; exits nonzero when required checks fail
- **Natural-language install**: README (EN + ZH) now leads with a one-sentence prompt users
  can paste into Claude Code / Codex to install and verify everything
- CI: GitHub Actions running offline tests on push/PR (Python 3.11–3.13)

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
