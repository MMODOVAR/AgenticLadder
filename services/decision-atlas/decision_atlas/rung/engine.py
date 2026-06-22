"""Rung-recommendation engine.

Given a decision's derived signals, recommend a target autonomy rung with an
explainable rationale. The model is deliberately transparent — a Chief
Transformation Officer must be able to read *why* a decision landed where it did
and challenge any single factor.

Two forces decide the rung:

* **Readiness** — a weighted blend of the enabler signals (volume,
  reversibility, data availability, determinism, historical consistency) maps to
  a *base* rung. The more ready a decision is, the higher the base.
* **Risk ceiling** — impact (blast radius) and regulatory sensitivity impose a
  hard cap. A high-stakes or heavily regulated decision cannot be recommended
  for high autonomy no matter how ready it otherwise looks.

The recommendation is ``min(base, ceiling)``, plus a confidence score driven by
how much real evidence (vs. heuristic defaults) backed the signals.
"""
from __future__ import annotations

from ..models import DecisionSignals, Provenance, RungRecommendation, Signal
from .ladder import MAX_RUNG, rung_name

# Weights for blending enabler signals into a readiness score. They sum to 1.0.
ENABLER_WEIGHTS = {
    "volume": 0.15,
    "reversibility": 0.25,
    "data_availability": 0.25,
    "determinism": 0.20,
    "historical_consistency": 0.15,
}

# Readiness thresholds -> base rung (upper bound of each band).
READINESS_BANDS = [
    (0.20, 0),
    (0.35, 1),
    (0.50, 2),
    (0.65, 3),
    (0.80, 4),
    (1.01, 5),
]

# Human-readable labels for signals in rationale text.
LABELS = {
    "volume": "decision volume",
    "reversibility": "reversibility",
    "data_availability": "input-data availability",
    "determinism": "outcome determinism",
    "historical_consistency": "historical consistency",
    "impact": "blast radius / impact",
    "regulatory_sensitivity": "regulatory sensitivity",
}


def _band(readiness: float) -> int:
    for threshold, rung in READINESS_BANDS:
        if readiness < threshold:
            return rung
    return MAX_RUNG


def _risk_ceiling(impact: float, regulatory: float) -> tuple[int, str]:
    """Return the highest rung allowed by risk, and the dominating reason."""
    risk = max(impact, regulatory)
    driver = "blast radius / impact" if impact >= regulatory else "regulatory sensitivity"
    if risk >= 0.85:
        return 2, driver
    if risk >= 0.65:
        return 3, driver
    if risk >= 0.45:
        return 4, driver
    return MAX_RUNG, driver


def _confidence(signals: DecisionSignals, event_count: int) -> float:
    """Trust in the recommendation: more derived/annotated signals + more
    evidence => higher confidence."""
    sigs = list(signals.as_map().values())
    grounded = sum(
        1 for s in sigs if s.provenance in (Provenance.DERIVED, Provenance.ANNOTATED)
    )
    grounded_frac = grounded / len(sigs)
    # Evidence weight saturates: 1 event ~ low, 50+ events ~ full.
    evidence = min(1.0, event_count / 50.0)
    return round(0.5 * grounded_frac + 0.5 * evidence, 3)


def recommend(signals: DecisionSignals, event_count: int = 0,
              target_override: int | None = None) -> RungRecommendation:
    enablers = signals.as_map()
    readiness = sum(
        ENABLER_WEIGHTS[name] * enablers[name].value for name in ENABLER_WEIGHTS
    )

    base = _band(readiness)
    ceiling, ceiling_driver = _risk_ceiling(
        signals.impact.value, signals.regulatory_sensitivity.value
    )
    recommended = min(base, ceiling)

    if recommended == ceiling and ceiling < base:
        limiting_factor = ceiling_driver
    else:
        # Identify the weakest enabler holding readiness back.
        weakest = min(ENABLER_WEIGHTS, key=lambda n: enablers[n].value)
        limiting_factor = LABELS[weakest]

    rationale = _build_rationale(signals, readiness, base, ceiling, recommended,
                                 ceiling_driver)

    confidence = _confidence(signals, event_count)

    if target_override is not None:
        recommended = max(0, min(MAX_RUNG, int(target_override)))
        rationale.insert(0, f"Owner override: target set to rung {recommended} "
                            f"({rung_name(recommended)}).")
        limiting_factor = "owner override"

    return RungRecommendation(
        recommended_rung=recommended,
        rung_name=rung_name(recommended),
        base_rung=base,
        ceiling_rung=ceiling,
        readiness_score=readiness,
        confidence=confidence,
        limiting_factor=limiting_factor,
        rationale=rationale,
    )


def _describe(value: float) -> str:
    if value >= 0.75:
        return "high"
    if value >= 0.45:
        return "moderate"
    return "low"


def _build_rationale(signals: DecisionSignals, readiness: float, base: int,
                     ceiling: int, recommended: int, ceiling_driver: str) -> list[str]:
    out: list[str] = []
    out.append(
        f"Readiness {readiness:.2f} -> base rung {base} ({rung_name(base)})."
    )
    m = signals.as_map()
    for name in DecisionSignals.ENABLERS:
        s: Signal = m[name]
        out.append(
            f"- {LABELS[name].capitalize()}: {_describe(s.value)} "
            f"({s.value:.2f}, {s.provenance.value})"
            + (f" — {s.note}" if s.note else "")
        )
    out.append(
        f"Risk ceiling: rung {ceiling} ({rung_name(ceiling)}), driven by "
        f"{ceiling_driver} "
        f"(impact {signals.impact.value:.2f}, "
        f"regulatory {signals.regulatory_sensitivity.value:.2f})."
    )
    if recommended < base:
        out.append(
            f"Recommendation capped at rung {recommended} ({rung_name(recommended)}) "
            f"by risk — start lower and climb as guardrails prove out."
        )
    else:
        out.append(
            f"Recommended target: rung {recommended} ({rung_name(recommended)})."
        )
    return out
