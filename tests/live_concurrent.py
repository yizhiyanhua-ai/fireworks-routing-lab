"""Concurrency test: N parallel processes (simulating sessions/subagents of one
tool) submit proposals with the SAME base_version simultaneously.

Asserts:
- every proposal lands exactly once (no lost update, no duplicate)
- versions are strictly sequential 1..N in the event log
- all committed items are present in the final document
- stale submitters were re-gated via still_applies (not blind-committed)

Run: .venv/bin/python test_concurrent.py
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steward import Proposal, Steward, history, init_store, load_canonical

ROOT = "/tmp/steward-concurrent"
N = 6


def worker(i: int, start_at: float) -> dict:
    import time
    while time.time() < start_at:  # maximize simultaneity without picklable sync primitives
        time.sleep(0.005)
    section = "next_actions" if i % 2 == 0 else "evidence_log"
    p = Proposal(
        author_tool="claude",
        author_ref=f"claude:session-demo:subagent-{i}",
        base_version=0,  # everyone read the doc at v0 before starting work
        section=section,
        operation="append",
        content=f"subagent-{i} 的工作产出 #{i}",
        summary=f"subagent-{i} 追加一条{'行动' if section == 'next_actions' else '证据'}",
    )
    return Steward(ROOT).submit(p)


def main() -> None:
    if os.path.exists(ROOT):
        shutil.rmtree(ROOT)
    init_store(ROOT, "goal-concurrent-test", "并发提交压测：同一工具多个 subagent 同时更新 handoff")

    import time
    start_at = time.time() + 2.0
    with mp.Pool(N) as pool:
        results = pool.starmap(worker, [(i, start_at) for i in range(N)])

    doc = load_canonical(ROOT)
    events = history(ROOT)
    commits = [e for e in events if e.get("type") == "commit"]
    versions = [e["new_version"] for e in commits]
    items = doc["next_actions"] + doc["evidence_log"]

    checks = []
    checks.append(("全部提案都 auto_commit", all(r["action"] == "auto_commit" for r in results)))
    checks.append((f"最终版本 = {N}", doc["meta"]["version"] == N))
    checks.append(("版本严格连续 1..N", versions == list(range(1, N + 1))))
    checks.append(("无丢失更新：6 条内容全部在文档中", len(items) == N and all(
        any(f"subagent-{i} " in x for x in items) for i in range(N))))
    stale = [r for r in results if r["gate"].get("still_applies") is not None]
    checks.append((f"后到者被 stale 重检（{len(stale)}/{N - 1} 个以上）", len(stale) >= N - 2))

    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print("\n版本序列:", versions)
    print("各提案路由:", [(r["action"], round(r["gate"]["merge_risk"], 2),
                          r["gate"].get("still_applies")) for r in results])
    ok_all = all(ok for _, ok in checks)
    print(f"\n===== {'ALL PASS' if ok_all else 'FAILED'} =====")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
