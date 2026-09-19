# Recipe: Session → Session handoff

One tool, many sessions over days. The store is the living handoff.

## Setup (once)

```bash
handoff-steward --root .handoff/goal-my-project init --goal-id goal-my-project --goal "…"
handoff-steward install-hooks   # SessionStart will inject store state into every new session
nohup handoff-steward --root .handoff/goal-my-project watch --interval 5 &
```

## The loop

1. **Session A** works; at each milestone it submits:
   `submit_proposal({"section": "current_state", "operation": "update", …})`
2. **Session B** opens later. The SessionStart hook has already injected:
   store version, active decisions, pending escalations. It does not ask you to summarize.
3. Session B submits an update that quietly reverses a decision from session A →
   `decision_conflict` fires → escalation brief → you rule → ruling submitted as a new decision.
4. `handoff-steward --root .handoff/goal-my-project history` is the full archaeology:
   every shift change, every ruling, every rejected stale proposal.

## Why not just a markdown handoff file?

A markdown file is a one-way snapshot that rots. The store checks semantic consistency
at write time, keeps superseded decisions, and proves which session wrote what
(`author_ref`).
