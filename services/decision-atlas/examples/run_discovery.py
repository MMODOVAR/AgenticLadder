"""End-to-end example: crawl the sample sources, print the decision map, and
export each domain's decision graph to Mermaid.

    cd services/decision-atlas
    python examples/run_discovery.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Make the package importable when run directly (python examples/run_discovery.py).
sys.path.insert(0, os.path.dirname(HERE))

from decision_atlas.discovery import DiscoveryEngine  # noqa: E402
from decision_atlas.graph import build_graph, to_mermaid  # noqa: E402

SAMPLE_DIR = os.path.join(os.path.dirname(HERE), "decision_atlas", "sample_data")
CONFIG = os.path.join(SAMPLE_DIR, "config.json")


def main() -> None:
    with open(CONFIG) as fh:
        config = json.load(fh)

    engine = DiscoveryEngine.from_config(config, base_dir=SAMPLE_DIR)
    domains = engine.discover()

    total = sum(len(d.decisions) for d in domains)
    print(f"Discovered {total} decisions across {len(domains)} domains\n")

    for dom in domains:
        print(f"== {dom.name} ==")
        for dec in dom.decisions:
            rec = dec.recommendation
            print(f"  {dec.name}")
            print(f"    sources: {', '.join(dec.sources)}")
            print(f"    inputs : {', '.join(dec.input_data) or '(none)'}")
            print(f"    target : Rung {rec.recommended_rung} ({rec.rung_name}) "
                  f"[base {rec.base_rung} / ceiling {rec.ceiling_rung}] "
                  f"confidence {rec.confidence:.2f}")
            print(f"    why    : {rec.limiting_factor} is the limiting factor")
        # Export the domain's decision graph as Mermaid.
        graph = build_graph(dom)
        out_path = os.path.join(HERE, f"{dom.name.replace(' ', '_')}.mmd")
        with open(out_path, "w") as fh:
            fh.write(to_mermaid(graph))
        print(f"    graph  : wrote {os.path.relpath(out_path)}\n")


if __name__ == "__main__":
    main()
