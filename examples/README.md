# Examples

Proposal JSON files that agents (Codex / Claude / Kimi / Pi) submit instead of
editing the handoff document directly.

```bash
export TYPESAFE_API_KEY=...   # from https://console.typesafe.ai/settings/keys

handoff-steward --root /tmp/demo-store init --goal-id goal-demo --goal "Demo goal"

# fill base_version with the version printed by `status` before each submit
handoff-steward --root /tmp/demo-store submit --proposal examples/proposals/append-decision.json
handoff-steward --root /tmp/demo-store status
handoff-steward --root /tmp/demo-store history
```

Field reference and verdict handling: see the main [README](../README.md#proposal-format).
