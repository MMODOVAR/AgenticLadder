import unittest

from decision_atlas.discovery import DiscoveryEngine
from decision_atlas.graph import build_graph, export
from decision_atlas.models import DecisionEvent


def ev(**kw):
    kw.setdefault("source", "s")
    kw.setdefault("source_type", "t")
    return DecisionEvent(**kw)


class TestGraph(unittest.TestCase):
    def _domain(self):
        events = [
            ev(id="1", decision_key="risk_score", domain="A", role="Analyst",
               input_fields=["raw_data"]),
            ev(id="2", decision_key="loan_decision", domain="A", role="Officer",
               input_fields=["risk_score", "income"]),
        ]
        return DiscoveryEngine().build_decisions(events)[0]

    def test_build_graph_nodes_and_edges(self):
        g = build_graph(self._domain())
        types = {n.type for n in g.nodes}
        self.assertIn("decision", types)
        self.assertIn("input", types)
        self.assertIn("owner", types)
        # dependency edge inferred: risk_score decision feeds loan_decision
        dep_edges = [e for e in g.edges if e.type == "depends"]
        self.assertTrue(dep_edges)

    def test_exports_all_formats(self):
        g = build_graph(self._domain())
        for fmt in ("json", "dot", "mermaid", "graphml"):
            out = export(g, fmt)
            self.assertIsInstance(out, str)
            self.assertTrue(out.strip())
        self.assertIn("digraph", export(g, "dot"))
        self.assertIn("flowchart", export(g, "mermaid"))
        self.assertIn("graphml", export(g, "graphml"))

    def test_unknown_format_raises(self):
        g = build_graph(self._domain())
        with self.assertRaises(ValueError):
            export(g, "svg")


if __name__ == "__main__":
    unittest.main()
