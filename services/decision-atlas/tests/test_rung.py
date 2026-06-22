import unittest

from decision_atlas.models import DecisionSignals, Provenance, Signal
from decision_atlas.rung.engine import recommend
from decision_atlas.rung.ladder import LADDER, MAX_RUNG, rung_name


def signals(**kw):
    s = DecisionSignals()
    for name, value in kw.items():
        setattr(s, name, Signal(value, Provenance.DERIVED))
    return s


class TestLadder(unittest.TestCase):
    def test_ladder_has_six_rungs(self):
        self.assertEqual(len(LADDER), 6)
        self.assertEqual(MAX_RUNG, 5)
        self.assertEqual(rung_name(0), "Manual")
        self.assertEqual(rung_name(5), "Full Autonomy")

    def test_rung_name_clamps(self):
        self.assertEqual(rung_name(99), "Full Autonomy")
        self.assertEqual(rung_name(-3), "Manual")


class TestRecommend(unittest.TestCase):
    def test_high_readiness_low_risk_recommends_high_rung(self):
        s = signals(volume=1.0, reversibility=1.0, data_availability=1.0,
                    determinism=1.0, historical_consistency=1.0,
                    impact=0.1, regulatory_sensitivity=0.1)
        rec = recommend(s, event_count=100)
        self.assertGreaterEqual(rec.recommended_rung, 4)
        self.assertEqual(rec.ceiling_rung, 5)

    def test_high_risk_caps_recommendation(self):
        s = signals(volume=1.0, reversibility=1.0, data_availability=1.0,
                    determinism=1.0, historical_consistency=1.0,
                    impact=0.95, regulatory_sensitivity=0.9)
        rec = recommend(s, event_count=100)
        self.assertEqual(rec.ceiling_rung, 2)
        self.assertLessEqual(rec.recommended_rung, 2)
        self.assertEqual(rec.recommended_rung, min(rec.base_rung, rec.ceiling_rung))
        self.assertIn(rec.limiting_factor,
                      ("blast radius / impact", "regulatory sensitivity"))

    def test_low_readiness_recommends_low_rung(self):
        s = signals(volume=0.0, reversibility=0.1, data_availability=0.0,
                    determinism=0.1, historical_consistency=0.1,
                    impact=0.2, regulatory_sensitivity=0.1)
        rec = recommend(s, event_count=1)
        self.assertLessEqual(rec.recommended_rung, 1)

    def test_target_override(self):
        s = signals(volume=1.0, reversibility=1.0, data_availability=1.0,
                    determinism=1.0, historical_consistency=1.0,
                    impact=0.1, regulatory_sensitivity=0.1)
        rec = recommend(s, event_count=100, target_override=2)
        self.assertEqual(rec.recommended_rung, 2)
        self.assertEqual(rec.limiting_factor, "owner override")

    def test_confidence_scales_with_evidence_and_provenance(self):
        derived = signals(volume=0.5, reversibility=0.5, data_availability=0.5,
                          determinism=0.5, historical_consistency=0.5,
                          impact=0.3, regulatory_sensitivity=0.3)
        high = recommend(derived, event_count=100)
        low = recommend(DecisionSignals(), event_count=1)  # all defaults
        self.assertGreater(high.confidence, low.confidence)
        self.assertLessEqual(high.confidence, 1.0)

    def test_recommendation_is_min_base_ceiling(self):
        s = signals(volume=1.0, reversibility=1.0, data_availability=1.0,
                    determinism=1.0, historical_consistency=1.0,
                    impact=0.5, regulatory_sensitivity=0.1)
        rec = recommend(s, event_count=50)
        self.assertEqual(rec.recommended_rung, min(rec.base_rung, rec.ceiling_rung))
        self.assertTrue(rec.rationale)


if __name__ == "__main__":
    unittest.main()
