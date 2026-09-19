# Recipe: Subagent result reporting

Parallel subagents report to the steward, not to the lead agent's prose summary.

## Dispatch prompt pattern

```
You are subagent-N of 5. Investigate <topic>. When done, submit your findings:
  submit_proposal({
    "section": "evidence_log", "operation": "append",
    "content": "<finding> — evidence: <path>",
    "summary": "<one line>",
    "author_ref": "<tool>:<session>:subagent-N",
  }, root=".handoff/goal-X")
Do NOT report back prose for me to merge; the steward is the merge point.
```

## What you get

- **Deterministic collection**: every finding lands exactly once, in arrival order,
  with the submitter's identity attached.
- **Contradiction surfacing**: subagent-1 says "the API streams", subagent-2 says "it
  doesn't" → the second submit sees elevated merge_risk / contradiction and escalates
  with both evidence links, instead of one silently overwriting the other.
- **Lead agent's role changes**: from copy-paste summarizer to referee that only
  processes `list_escalations`.

## Verify

```bash
handoff-steward --root .handoff/goal-X history   # who submitted what, what was rejected
```

See `tests/live_concurrent.py`: 6 processes, same base_version, zero lost updates.
