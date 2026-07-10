"""RungGuard CLI.

Usage
-----
python -m rungguard <command> [options]

Commands
--------
serve       Start the REST API + dashboard
register    Register a new agent
promote     Submit a rung-promotion change request
demote      Submit a rung-demotion change request
suspend     Submit a suspension request
check       Evaluate whether an agent may perform an action
audit       Print the recent audit log
ladder      Display the autonomy ladder
"""
from __future__ import annotations

import argparse
import json
import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plane():
    from .api.store import ControlPlane
    return ControlPlane()


def _json(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_ladder(_args: argparse.Namespace) -> None:
    from .policies.rules import RUNG_POLICIES

    rows = [
        ("Rung", "Name", "Allowed categories", "Rate limit", "Financial cap"),
        ("----", "----", "------------------", "----------", "-------------"),
    ]
    names = {
        0: "Manual",
        1: "Assisted",
        2: "Recommended",
        3: "Supervised",
        4: "Conditional Autonomy",
        5: "Full Autonomy",
    }
    for rung, policy in sorted(RUNG_POLICIES.items()):
        cats = ", ".join(c.value for c in policy.allowed_actions) or "(none)"
        rate = (
            f"{min(policy.rate_limits.values())}/min"
            if policy.rate_limits
            else "unlimited"
        )
        cap = (
            f"${policy.max_financial_amount:,.0f}"
            if policy.max_financial_amount is not None
            else "unlimited"
        )
        rows.append((str(rung), names.get(rung, "?"), cats, rate, cap))

    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for row in rows:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def cmd_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required to run the server. Install with: pip install uvicorn", file=sys.stderr)
        sys.exit(1)
    uvicorn.run(
        "rungguard.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def cmd_register(args: argparse.Namespace) -> None:
    plane = _plane()
    agent = plane.register_agent(
        name=args.name,
        owner=args.owner,
        owner_email=args.owner_email or "",
        description=args.description or "",
        initial_rung=args.rung,
        tags=dict(t.split("=", 1) for t in (args.tags or [])),
    )
    _json(agent.to_dict())


def cmd_promote(args: argparse.Namespace) -> None:
    plane = _plane()
    req = plane.submit_change_request(
        agent_id=args.agent_id,
        to_rung=args.to_rung,
        requested_by=args.requested_by,
        justification=args.justification,
    )
    _json(req.to_dict())


def cmd_demote(args: argparse.Namespace) -> None:
    from .models import ChangeDirection
    plane = _plane()
    req = plane.submit_change_request(
        agent_id=args.agent_id,
        to_rung=args.to_rung,
        requested_by=args.requested_by,
        justification=args.justification,
        direction=ChangeDirection.DEMOTION,
    )
    _json(req.to_dict())


def cmd_suspend(args: argparse.Namespace) -> None:
    from .models import ChangeDirection
    plane = _plane()
    req = plane.submit_change_request(
        agent_id=args.agent_id,
        to_rung=0,
        requested_by=args.requested_by,
        justification=args.justification,
        direction=ChangeDirection.SUSPENSION,
    )
    _json(req.to_dict())


def cmd_check(args: argparse.Namespace) -> None:
    plane = _plane()
    ctx: dict = {}
    for kv in (args.context or []):
        k, _, v = kv.partition("=")
        ctx[k.strip()] = v.strip()
    result = plane.check_action(args.agent_id, args.action, ctx)
    _json(result.to_dict())


def cmd_audit(args: argparse.Namespace) -> None:
    plane = _plane()
    entries = plane.audit.recent(args.limit)
    for e in entries:
        d = e.to_dict()
        ts = d.get("timestamp", "")[:19]
        outcome = d.get("outcome", "")
        action = d.get("action", d.get("event_type", ""))
        agent = d.get("agent_id", "")[:8]
        rung = d.get("rung_at_time", "?")
        print(f"{ts}  [{outcome:12s}]  agent={agent}  rung={rung}  action={action}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rungguard",
        description="RungGuard autonomy-rung governance control plane",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ladder
    p = sub.add_parser("ladder", help="Display the autonomy ladder and policies")
    p.set_defaults(func=cmd_ladder)

    # serve
    p = sub.add_parser("serve", help="Start the REST API + dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    # register
    p = sub.add_parser("register", help="Register a new agent")
    p.add_argument("name")
    p.add_argument("--owner", required=True)
    p.add_argument("--owner-email")
    p.add_argument("--description")
    p.add_argument("--rung", type=int, default=0)
    p.add_argument("--tag", dest="tags", action="append", metavar="KEY=VALUE")
    p.set_defaults(func=cmd_register)

    # promote
    p = sub.add_parser("promote", help="Submit a rung-promotion change request")
    p.add_argument("agent_id")
    p.add_argument("to_rung", type=int)
    p.add_argument("--by", dest="requested_by", required=True)
    p.add_argument("--justification", required=True)
    p.set_defaults(func=cmd_promote)

    # demote
    p = sub.add_parser("demote", help="Submit a rung-demotion change request")
    p.add_argument("agent_id")
    p.add_argument("to_rung", type=int)
    p.add_argument("--by", dest="requested_by", required=True)
    p.add_argument("--justification", required=True)
    p.set_defaults(func=cmd_demote)

    # suspend
    p = sub.add_parser("suspend", help="Submit a suspension request (forces rung 0)")
    p.add_argument("agent_id")
    p.add_argument("--by", dest="requested_by", required=True)
    p.add_argument("--justification", required=True)
    p.set_defaults(func=cmd_suspend)

    # check
    p = sub.add_parser("check", help="Evaluate whether an agent may perform an action")
    p.add_argument("agent_id")
    p.add_argument("action")
    p.add_argument("--context", action="append", metavar="KEY=VALUE")
    p.set_defaults(func=cmd_check)

    # audit
    p = sub.add_parser("audit", help="Print recent audit log entries")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_audit)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
