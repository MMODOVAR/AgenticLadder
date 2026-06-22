import os
import unittest

from decision_atlas.discovery import DiscoveryEngine, derive_signals
from decision_atlas.models import DecisionEvent, Provenance

SAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "decision_atlas", "sample_data"
)


def ev(**kw):
    kw.setdefault("source", "s")
    kw.setdefault("source_type", "t")
    return DecisionEvent(**kw)


class TestSignals(unittest.TestCase):
    def test_volume_and_consistency_derivation(self):
        events = [ev(id=str(i), decision_key="d", outcome="approved",
                     overturned=(i == 0), input_fields=["a", "b", "c"])
                  for i in range(10)]
        sig = derive_signals(events)
        self.assertEqual(sig.volume.provenance, Provenance.DERIVED)
        self.assertGreater(sig.volume.value, 0)
        # 1 of 10 overturned -> consistency 0.9
        self.assertAlmostEqual(sig.historical_consistency.value, 0.9, places=2)
        # all outcomes "approved" -> determinism 1.0
        self.assertAlmostEqual(sig.determinism.value, 1.0, places=2)

    def test_regulatory_keyword_raises_sensitivity(self):
        events = [ev(id="1", decision_key="finance.payment_approval",
                     input_fields=["amount"])]
        sig = derive_signals(events)
        self.assertGreaterEqual(sig.regulatory_sensitivity.value, 0.8)

    def test_empty_events_returns_defaults(self):
        sig = derive_signals([])
        self.assertEqual(sig.volume.value, 0.0)


class TestDiscoveryEngine(unittest.TestCase):
    def test_clusters_by_domain_and_key(self):
        events = [
            ev(id="1", decision_key="x", domain="A"),
            ev(id="2", decision_key="x", domain="A"),
            ev(id="3", decision_key="x", domain="B"),
            ev(id="4", decision_key="y", domain="A"),
        ]
        domains = DiscoveryEngine().build_decisions(events)
        names = {d.name: d for d in domains}
        self.assertEqual(set(names), {"A", "B"})
        self.assertEqual(len(names["A"].decisions), 2)
        self.assertEqual(len(names["B"].decisions), 1)
        # decision x in A has 2 events
        x = next(d for d in names["A"].decisions if d.key == "x")
        self.assertEqual(x.event_count, 2)
        self.assertIsNotNone(x.recommendation)

    def test_sorted_by_event_count(self):
        events = [ev(id=str(i), decision_key="big", domain="A") for i in range(5)]
        events += [ev(id="z", decision_key="small", domain="A")]
        domains = DiscoveryEngine().build_decisions(events)
        decisions = domains[0].decisions
        self.assertEqual(decisions[0].key, "big")

    def test_end_to_end_from_sample_config(self):
        import json
        path = os.path.join(SAMPLE_DIR, "config.json")
        with open(path) as fh:
            config = json.load(fh)
        engine = DiscoveryEngine.from_config(config, base_dir=SAMPLE_DIR)
        domains = engine.discover()
        self.assertTrue(domains)
        all_decisions = [d for dom in domains for d in dom.decisions]
        self.assertGreater(len(all_decisions), 3)
        # Every decision has a recommendation within range.
        for d in all_decisions:
            self.assertIsNotNone(d.recommendation)
            self.assertTrue(0 <= d.recommendation.recommended_rung <= 5)
        # Wire transfer (regulated, high amount) should be capped low.
        names = {d.key: d for d in all_decisions}
        wire = names.get("wire_transfer.approval")
        self.assertIsNotNone(wire)
        self.assertLessEqual(wire.recommendation.recommended_rung, 2)


if __name__ == "__main__":
    unittest.main()
