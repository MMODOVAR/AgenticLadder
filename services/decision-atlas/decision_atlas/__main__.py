"""Decision Atlas command line.

    python -m decision_atlas discover --config sample_data/config.json
    python -m decision_atlas export  --config sample_data/config.json --domain Finance --format mermaid
    python -m decision_atlas serve   --port 8000
    python -m decision_atlas ladder
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .discovery import DiscoveryEngine
from .graph import build_graph, export
from .rung.ladder import LADDER

DEFAULT_CONFIG = os.path.join(os.path.dirname(__file__), "sample_data", "config.json")


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_discover(args: argparse.Namespace) -> int:
    engine = DiscoveryEngine.from_config(
        _load_config(args.config), base_dir=os.path.dirname(os.path.abspath(args.config)))
    domains = engine.discover()
    if args.json:
        print(json.dumps({"domains": [d.to_dict() for d in domains]}, indent=2))
        return 0
    total = sum(len(d.decisions) for d in domains)
    print(f"Discovered {total} decisions across {len(domains)} domain(s):\n")
    for dom in domains:
        print(f"  ▸ {dom.name} ({len(dom.decisions)} decisions)")
        for dec in dom.decisions:
            rec = dec.recommendation
            tag = f"Rung {rec.recommended_rung} ({rec.rung_name})" if rec else "n/a"
            print(f"      - {dec.name:<32} {dec.event_count:>4} events  "
                  f"→ {tag}  conf={rec.confidence:.2f}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    engine = DiscoveryEngine.from_config(
        _load_config(args.config), base_dir=os.path.dirname(os.path.abspath(args.config)))
    domains = engine.discover()
    target = next((d for d in domains if d.name.lower() == args.domain.lower()), None)
    if target is None:
        print(f"Domain not found: {args.domain}. "
              f"Available: {', '.join(d.name for d in domains)}", file=sys.stderr)
        return 1
    graph = build_graph(target)
    out = export(graph, args.format)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"Wrote {args.out}")
    else:
        print(out)
    return 0


def cmd_ladder(_: argparse.Namespace) -> int:
    print("AgenticLadder — autonomy ladder\n")
    for r in LADDER:
        print(f"  Rung {r.level} · {r.name}")
        print(f"      {r.summary}")
        print(f"      Human: {r.human_role}\n")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn/fastapi required: pip install fastapi uvicorn", file=sys.stderr)
        return 1
    uvicorn.run("decision_atlas.api.app:app", host=args.host, port=args.port,
                reload=args.reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="decision_atlas", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("discover", help="Crawl sources and print the decision map")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--json", action="store_true", help="Emit full JSON")
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("export", help="Export a domain's decision graph")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--domain", required=True)
    p.add_argument("--format", default="mermaid",
                   choices=["json", "dot", "mermaid", "graphml"])
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("ladder", help="Print the autonomy ladder")
    p.set_defaults(func=cmd_ladder)

    p = sub.add_parser("serve", help="Run the API + dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
