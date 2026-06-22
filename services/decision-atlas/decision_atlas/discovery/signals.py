"""Derive decision signals from observed evidence.

Each signal is computed from the cluster of events that make up a decision. When
there is enough evidence we mark the signal ``DERIVED``; otherwise we fall back
to a heuristic ``DEFAULT`` that the domain owner can override during annotation.
This provenance is what the rung engine uses to set its confidence.
"""
from __future__ import annotations

import re
from collections import Counter

from ..models import DecisionEvent, DecisionSignals, Provenance, Signal, log_scale

# Keyword heuristics for regulatory sensitivity, scanned over key + inputs.
REGULATED_PATTERNS = re.compile(
    r"\b(gdpr|sox|hipaa|pci|pii|kyc|aml|credit|payment|payout|refund|tax|"
    r"compliance|legal|privacy|consent|medical|health|salary|payroll|"
    r"loan|insurance|fraud|sanction)\b",
    re.IGNORECASE,
)

# Keyword heuristics for high blast radius when no explicit impact is present.
HIGH_IMPACT_PATTERNS = re.compile(
    r"\b(prod|production|delete|terminate|shutdown|wire|transfer|deploy|"
    r"release|grant|revoke|access|admin|root|disburse)\b",
    re.IGNORECASE,
)


def derive_signals(events: list[DecisionEvent]) -> DecisionSignals:
    sig = DecisionSignals()
    n = len(events)
    if n == 0:
        return sig

    # --- volume (enabler) ---------------------------------------------------
    sig.volume = Signal(
        log_scale(n), Provenance.DERIVED, f"{n} observed decision events"
    ).clamp()

    # --- reversibility (enabler) -------------------------------------------
    rev_known = [e.reversible for e in events if e.reversible is not None]
    if rev_known:
        frac = sum(1 for r in rev_known if r) / len(rev_known)
        sig.reversibility = Signal(
            frac, Provenance.DERIVED,
            f"{sum(rev_known)}/{len(rev_known)} actions reversible"
        ).clamp()

    # --- data availability (enabler) ---------------------------------------
    field_counts = [len(e.input_fields) for e in events]
    avg_fields = sum(field_counts) / n if field_counts else 0
    if any(field_counts):
        # 6+ structured inputs -> fully available.
        sig.data_availability = Signal(
            min(1.0, avg_fields / 6.0), Provenance.DERIVED,
            f"~{avg_fields:.1f} structured inputs per decision"
        ).clamp()

    # --- determinism (enabler) ---------------------------------------------
    outcomes = Counter(e.outcome for e in events if e.outcome)
    if outcomes:
        top = outcomes.most_common(1)[0][1]
        concentration = top / sum(outcomes.values())
        sig.determinism = Signal(
            concentration, Provenance.DERIVED,
            f"dominant outcome covers {concentration:.0%} of cases"
        ).clamp()

    # --- historical consistency (enabler) ----------------------------------
    over_known = [e.overturned for e in events if e.overturned is not None]
    if over_known:
        override_rate = sum(1 for o in over_known if o) / len(over_known)
        sig.historical_consistency = Signal(
            1.0 - override_rate, Provenance.DERIVED,
            f"{override_rate:.0%} of decisions later overturned"
        ).clamp()

    # --- impact (risk) ------------------------------------------------------
    impacts = [e.impact for e in events if e.impact is not None]
    # Normalize separators (._-) to spaces so word-boundary keyword matching
    # works on identifiers like "finance.payment_approval".
    raw_text = " ".join(filter(None, [
        events[0].decision_key,
        *(events[0].input_fields or []),
    ]))
    text = re.sub(r"[._\-/]+", " ", raw_text)
    if impacts:
        sig.impact = Signal(
            max(impacts), Provenance.DERIVED,
            f"peak observed impact {max(impacts):.2f}"
        ).clamp()
    elif HIGH_IMPACT_PATTERNS.search(text):
        sig.impact = Signal(
            0.8, Provenance.DEFAULT,
            "high-impact keyword detected in decision/inputs"
        ).clamp()

    # --- regulatory sensitivity (risk) -------------------------------------
    if REGULATED_PATTERNS.search(text):
        sig.regulatory_sensitivity = Signal(
            0.85, Provenance.DEFAULT,
            "regulated-domain keyword detected — confirm with owner"
        ).clamp()

    return sig
