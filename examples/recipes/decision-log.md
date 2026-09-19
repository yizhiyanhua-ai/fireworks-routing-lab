# Recipe: A shared decision log with teeth

The `decisions` section is a runtime-enforced ADR system across tools and sessions.

## Recording a decision

```json
{
  "section": "decisions", "operation": "append",
  "content": {"text": "State storage uses PostgreSQL; document stores are out of scope"},
  "summary": "Architecture decision: PostgreSQL"
}
```

The store assigns `D-1`. From now on, every new decision proposal is fan-out checked
against all active decisions via Jev Noul questions.

## When a contradiction arrives

Any tool proposing "switch to MongoDB" gets:

```
escalate — decision conflict: D-1 p=0.98
brief: <store>/escalations/esc-….json   (both sides + Jev probabilities)
```

You rule. Either the proposal is rejected, or D-1 is superseded:

```json
{
  "section": "decisions", "operation": "update",
  "content": {"id": "D-1", "text": "…revised decision…"},
  "summary": "human ruling: supersede D-1 because …"
}
```

## Why it beats ADR markdown files

- **Enforced at write time**, not dependent on anyone remembering to read the ADRs
- Superseded decisions keep full text and history — answer "when / by whom / replaced
  by what" from `history` alone
- The conflict check is semantic (Jev), not keyword-based: "abandon PostgreSQL" and
  "use MongoDB for everything" both match D-1 without naming it
