"""CLI: init / submit / status / history / reconcile / watch / install-skill / doctor."""
from __future__ import annotations

import argparse
import json
import sys

from . import install, store, watchdog
from .schema import Proposal
from .steward import Steward


def main() -> None:
    ap = argparse.ArgumentParser(prog="steward")
    ap.add_argument("--root", help="store directory for the handoff (not needed for install-skill/doctor)")
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

    p = sub.add_parser("install-skill", help="install the bundled agent skill into agent skill dirs")
    p.add_argument("--target", action="append", help="explicit skills dir; repeatable. Default: auto-detect")
    p.add_argument("--create", action="store_true", help="create agent skill dirs that do not exist yet")

    p = sub.add_parser("install-mcp", help="register the MCP server with coding agents")
    p.add_argument("--agent", action="append", help="claude|codex|cursor|gemini; repeatable. Default: all")

    p = sub.add_parser("mcp", help="run the MCP server (stdio). Requires: pip install handoff-steward[mcp]")

    p = sub.add_parser("hook", help="hook handler: reads hook JSON from stdin")
    p.add_argument("name", choices=["guard", "session-start", "subagent-stop", "file-changed"])

    p = sub.add_parser("install-hooks", help="wire hooks into agent configs")
    p.add_argument("--agent", action="append", help="claude|cursor; repeatable. Default: both")

    p = sub.add_parser("doctor", help="check install readiness")
    p.add_argument("--live", action="store_true", help="also ping the TypeSafe API")
    p.add_argument("--mcp", action="store_true", help="also check MCP registrations")
    p.add_argument("--target", action="append", help="explicit skills dir to check; repeatable")

    args = ap.parse_args()

    if args.cmd == "install-skill":
        results = install.install_skill(targets=args.target, create=args.create)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        failed = [r for r in results if r["status"].startswith("skipped")]
        if results and len(failed) == len(results):
            print("No agent skill dirs found. Re-run with --create or --target <dir>.", file=sys.stderr)
            sys.exit(1)
        return

    if args.cmd == "doctor":
        report = install.doctor(live=args.live, targets=args.target, mcp=args.mcp)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        sys.exit(0 if report["ok"] else 1)

    if args.cmd == "install-mcp":
        results = install.install_mcp(agents=args.agent)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        if any(r["status"].startswith("error") for r in results):
            sys.exit(1)
        return

    if args.cmd == "mcp":
        from . import mcp_server
        mcp_server.main()
        return

    if args.cmd == "hook":
        from . import hooks
        hooks.run_hook(args.name)
        return

    if args.cmd == "install-hooks":
        from . import hooks
        agents = args.agent or ["claude", "cursor"]
        print(json.dumps([{"agent": a, "status": hooks.install_hooks(a)} for a in agents],
                         ensure_ascii=False, indent=2))
        return

    if not args.root:
        ap.error(f"--root is required for '{args.cmd}'")

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
