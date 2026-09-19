# Changelog

## [0.2.0] - 2026-09-19

### Added
- **MCP server** (`handoff-steward mcp`, extra `[mcp]`): native tools for coding agents —
  `submit_proposal`, `get_status`, `get_history`, `list_escalations`, `init_store`
- **`handoff-steward install-mcp`**: registers the server with Claude Code (CLI or
  ~/.claude.json), Codex (config.toml), Cursor (mcp.json), Gemini (settings.json)
- **Agent hooks** (`handoff-steward hook …`): `guard` (PreToolUse deny for direct store
  writes), `session-start` (inject store state), `subagent-stop` (reporting reminder),
  `file-changed` (post-write reconcile, e.g. Cursor afterFileEdit)
- **`handoff-steward install-hooks`**: merges hook config into Claude settings.json and
  Cursor hooks.json, idempotent, never clobbers existing entries
- **`doctor --mcp`**: checks MCP registrations per agent
- README (EN/ZH): MCP/hooks section + three single-agent scenarios
  (session handoff, subagent reporting, decision log) + examples/recipes/
- **Bundled agent skill** (`steward/assets/handoff-steward/SKILL.md`), `install-skill`,
  `doctor`, natural-language install prompts, GitHub Actions CI
- 6 new offline tests (18 total)

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
