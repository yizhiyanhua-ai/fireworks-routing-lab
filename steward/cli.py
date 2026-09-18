"""CLI: init / submit / status / history / reconcile / watch."""
from __future__ import annotations

import argparse
import json
import sys

from . import store, watchdog
from .schema import Proposal
from .steward import Steward


def main() -> None:
    ap = argparse.ArgumentParser(prog="steward")
    ap.add_argument("--root", required=True, help="store directory for the handoff")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--goal-id", required=True)
    p.add_argument("--goal", required=True)

    p = sub.add_parser("submit")
    p.add_argument("--proposal", required=True, help="path to proposal JSON")

    sub.add_parser("status")
    sub.add_parser("history")

    p = sub.add_parser("reconcile")

    p = sub.add_parser("watch")
    p.add_argument("--interval", type=float, default=5.0)

    args = ap.parse_args()

    if args.cmd == "init":
        doc = store.init_store(args.root, args.goal_id, args.goal)
        watchdog.baseline(args.root)
        print(json.dumps({"initialized": True, "version": doc["meta"]["version"]}))
        return

    if args.cmd == "submit":
        with open(args.proposal) as f:
            proposal = Proposal.from_dict(json.load(f))
        result = Steward(args.root).submit(proposal)
        watchdog.baseline(args.root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.cmd == "status":
        doc = store.load_canonical(args.root)
        print(json.dumps({
            "version": doc["meta"]["version"],
            "updated_at": doc["meta"]["updated_at"],
            "updated_by": doc["meta"]["updated_by"],
            "decisions": len(doc["decisions"]),
            "open_questions": len(doc["open_questions"]),
            "next_actions": len(doc["next_actions"]),
        }, ensure_ascii=False, indent=2))
        return

    if args.cmd == "history":
        for e in store.history(args.root):
            print(json.dumps(e, ensure_ascii=False))
        return

    if args.cmd == "reconcile":
        print(json.dumps(watchdog.reconcile(args.root), ensure_ascii=False, indent=2))
        return

    if args.cmd == "watch":
        watchdog.watch(args.root, args.interval)


if __name__ == "__main__":
    main()
