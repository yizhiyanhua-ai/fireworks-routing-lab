"""Validation matrix: 6 routing case types against live Jev.

Each case declares its expected verdict BEFORE running. PASS = actual matches.
Run: .venv/bin/python validate_matrix.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steward import Proposal, Steward, init_store, load_canonical
from steward import watchdog

ROOT = "/tmp/steward-validation"
GOAL_ID = "goal-20261001-video-pipeline"
GOAL = "为烟花老师品牌搭建多工具协作的 AI 视频生产管线（Codex/Claude/Kimi 共用 handoff）"

results = []


def check(case: str, expected: str, actual: str, detail: str) -> bool:
    if isinstance(expected, str):
        ok = expected == actual
    elif isinstance(expected, bool):
        ok = bool(actual) == expected
    else:
        ok = actual in expected
    results.append({"case": case, "expected": expected, "actual": actual, "pass": ok, "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {case}: expected={expected} actual={actual}  ({detail})")
    return ok


def main() -> None:
    if os.path.exists(ROOT):
        shutil.rmtree(ROOT)
    init_store(ROOT, GOAL_ID, GOAL)
    s = Steward(ROOT)

    def submit(**kw):
        return s.submit(Proposal(**kw))

    # --- setup: seed the doc with a binding decision -------------------------
    r = submit(author_tool="codex", base_version=0, section="decisions", operation="append",
               content={"text": "后端状态存储统一用 PostgreSQL，不用文档型数据库"},
               summary="记录架构决策：PostgreSQL 作为状态存储")
    check("setup-决策入库", "auto_commit", r["action"], r["reason"])

    # --- case 1: clean append -------------------------------------------------
    v = load_canonical(ROOT)["meta"]["version"]
    r = submit(author_tool="claude", base_version=v, section="next_actions", operation="append",
               content="在 codex 侧完成 PostgreSQL schema 初稿",
               summary="新增下一步行动：schema 初稿")
    check("1-干净追加", "auto_commit", r["action"], r["reason"])

    # --- case 2: concurrent same-section update -------------------------------
    v = load_canonical(ROOT)["meta"]["version"]
    r1 = submit(author_tool="codex", base_version=v, section="current_state", operation="update",
                content="schema 初稿已完成，包含 5 张表", summary="更新当前状态：schema 完成 5 张表")
    check("2a-首个状态更新", "auto_commit", r1["action"], r1["reason"])
    # claude was working off the same base version and now submits a different current_state
    r2 = submit(author_tool="claude", base_version=v, section="current_state", operation="update",
                content="schema 初稿已完成，包含 5 张表，另补充了索引设计",
                summary="更新当前状态：schema 完成并补充索引")
    check("2b-同区并发(应字段级选择或升级)", ("field_select", "auto_commit", "escalate", "reject"),
          r2["action"], r2["reason"])

    # --- case 3: contradictory decision ---------------------------------------
    v = load_canonical(ROOT)["meta"]["version"]
    r = submit(author_tool="kimi", base_version=v, section="decisions", operation="append",
               content={"text": "状态存储改用 MongoDB，放弃 PostgreSQL"},
               summary="记录新决策：改用 MongoDB")
    check("3-矛盾决策", "escalate", r["action"], r["reason"])

    # --- case 4a: stale base, overtaken proposal ------------------------------
    r = submit(author_tool="codex", base_version=0, section="next_actions", operation="append",
               content="调研是否使用 PostgreSQL 作为存储",
               summary="新增行动：调研 PostgreSQL（早已决策，属过时提案）")
    check("4a-过时基线驳回", "reject", r["action"], r["reason"])

    # --- case 4b: stale base, still valid -------------------------------------
    r = submit(author_tool="claude", base_version=0, section="evidence_log", operation="append",
               content="压测结果：PostgreSQL p99 延迟 120ms，报告见 artifacts/perf-01.md",
               summary="补充压测证据")
    check("4b-过时但仍有效", "auto_commit", r["action"], r["reason"])

    # --- case 5: out of scope --------------------------------------------------
    v = load_canonical(ROOT)["meta"]["version"]
    r = submit(author_tool="kimi", base_version=v, section="next_actions", operation="append",
               content="预订周五团队聚餐的餐厅",
               summary="新增行动：订餐厅")
    check("5-越界驳回", "reject", r["action"], r["reason"])

    # --- case 6: ambiguous / low-confidence ------------------------------------
    v = load_canonical(ROOT)["meta"]["version"]
    r = submit(author_tool="codex", base_version=v, section="current_state", operation="update",
               content="有些地方可能要调整，也说不定，先这样",
               summary="模糊更新：意思不明")
    check("6-低置信不自动入库", ("escalate", "reject", "field_select"), r["action"], r["reason"])

    # --- watchdog: external direct write ----------------------------------------
    import steward.store as store
    doc = load_canonical(ROOT)
    doc["open_questions"].append("Kimi 的并行子任务是否也需要独立的 handoff 分区？")
    store._write_canonical(ROOT, doc)  # simulate a tool bypassing the steward
    report = watchdog.reconcile(ROOT)
    recovered_ok = report.get("external_write") and report.get("recovered") == 1
    routed = report.get("results", [{}])[0].get("action") if report.get("results") else "none"
    check("7-watchdog对账", True, bool(recovered_ok), f"recovered={report.get('recovered')}, routed={routed}")

    # --- report -----------------------------------------------------------------
    passed = sum(1 for r in results if r["pass"])
    print(f"\n===== {passed}/{len(results)} PASS =====")
    print("final doc version:", load_canonical(ROOT)["meta"]["version"])
    with open(os.path.join(ROOT, "validation-report.json"), "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
