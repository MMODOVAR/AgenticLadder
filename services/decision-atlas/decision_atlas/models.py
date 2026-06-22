"""Canonical, source-agnostic data model for Decision Atlas.

Every connector — regardless of cloud, language, or application — normalizes its
raw records into these structures. The discovery engine, rung-recommendation
engine, and graph exporters all operate purely on this canonical model, which is
what lets Decision Atlas work uniformly across heterogeneous enterprises.

This module intentionally depends only on the Python standard library so the
core engine can be imported, tested, and embedded anywhere without installing
third-party packages.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Raw observation
# ---------------------------------------------------------------------------


@dataclass
class DecisionEvent:
    """A single observed act of deciding, pulled from a source system.

    A ticket transition, an approval/rejection, a workflow task completion, or
    an audit-log entry all map onto this shape.
    """

    id: str
    source: str  # e.g. "jira-prod", "servicenow", "audit-s3"
    source_type: str  # connector type, e.g. "jira", "approval", "audit_log"
    decision_key: str  # normalized decision-type identifier, e.g. "refund.approval"
    timestamp: Optional[datetime] = None
    actor: Optional[str] = None  # who took the action
    role: Optional[str] = None  # actor's role/title if known
    action: Optional[str] = None  # e.g. "approve", "reject", "escalate", "close"
    outcome: Optional[str] = None  # resolved outcome value, e.g. "approved"
    domain: Optional[str] = None  # business domain, e.g. "Finance"
    input_fields: list[str] = field(default_factory=list)  # data feeding the decision
    reversible: Optional[bool] = None  # was this action reversible / rolled back-able
    overturned: Optional[bool] = None  # was this decision later reversed/overridden
    impact: Optional[float] = None  # 0..1 blast radius hint (severity/priority/$)
    raw: dict[str, Any] = field(default_factory=dict)  # original record for audit

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp.isoformat()
        return d


# ---------------------------------------------------------------------------
# Derived signals
# ---------------------------------------------------------------------------


class Provenance(str, Enum):
    """Where a signal value came from. Drives trust in the recommendation."""

    DERIVED = "derived"  # computed from observed evidence
    DEFAULT = "default"  # heuristic fallback, no evidence
    ANNOTATED = "annotated"  # set by the domain owner


@dataclass
class Signal:
    value: float  # 0..1
    provenance: Provenance = Provenance.DEFAULT
    note: str = ""

    def clamp(self) -> "Signal":
        self.value = max(0.0, min(1.0, self.value))
        return self


@dataclass
class DecisionSignals:
    """The seven factors that drive an autonomy-rung recommendation.

    Enablers push the rung *up* (more autonomy is feasible/valuable).
    Risks pull the ceiling *down* (more autonomy is dangerous).
    """

    # Enablers
    volume: Signal = field(default_factory=lambda: Signal(0.0))
    reversibility: Signal = field(default_factory=lambda: Signal(0.5))
    data_availability: Signal = field(default_factory=lambda: Signal(0.3))
    determinism: Signal = field(default_factory=lambda: Signal(0.5))
    historical_consistency: Signal = field(default_factory=lambda: Signal(0.5))
    # Risks
    impact: Signal = field(default_factory=lambda: Signal(0.5))
    regulatory_sensitivity: Signal = field(default_factory=lambda: Signal(0.3))

    ENABLERS = ("volume", "reversibility", "data_availability",
                "determinism", "historical_consistency")
    RISKS = ("impact", "regulatory_sensitivity")

    def as_map(self) -> dict[str, Signal]:
        return {
            "volume": self.volume,
            "reversibility": self.reversibility,
            "data_availability": self.data_availability,
            "determinism": self.determinism,
            "historical_consistency": self.historical_consistency,
            "impact": self.impact,
            "regulatory_sensitivity": self.regulatory_sensitivity,
        }

    def to_dict(self) -> dict[str, Any]:
        return {k: {"value": round(s.value, 3),
                    "provenance": s.provenance.value,
                    "note": s.note}
                for k, s in self.as_map().items()}


# ---------------------------------------------------------------------------
# Autonomy ladder + recommendation
# ---------------------------------------------------------------------------


@dataclass
class RungRecommendation:
    recommended_rung: int
    rung_name: str
    base_rung: int  # rung implied by enabler readiness alone
    ceiling_rung: int  # rung cap imposed by risk
    readiness_score: float  # 0..1
    confidence: float  # 0..1 — how much to trust this, given evidence
    limiting_factor: str
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["readiness_score"] = round(self.readiness_score, 3)
        d["confidence"] = round(self.confidence, 3)
        return d


# ---------------------------------------------------------------------------
# Owner annotation + approval
# ---------------------------------------------------------------------------


class Status(str, Enum):
    DISCOVERED = "discovered"  # auto-built, untouched
    ANNOTATED = "annotated"  # owner has edited
    APPROVED = "approved"  # owner signed off


@dataclass
class Annotation:
    owner: Optional[str] = None
    owner_role: Optional[str] = None
    criteria: Optional[str] = None  # what "correct" looks like
    notes: Optional[str] = None
    # owner overrides for any signal value, keyed by signal name -> 0..1
    signal_overrides: dict[str, float] = field(default_factory=dict)
    target_rung_override: Optional[int] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Aggregated decision
# ---------------------------------------------------------------------------


@dataclass
class Decision:
    """A decision *type* discovered across many events."""

    id: str
    key: str
    name: str
    domain: str = "Unassigned"
    description: str = ""
    owner: Optional[str] = None
    owner_role: Optional[str] = None
    criteria: Optional[str] = None
    input_data: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    actors: list[str] = field(default_factory=list)
    event_count: int = 0
    signals: DecisionSignals = field(default_factory=DecisionSignals)
    recommendation: Optional[RungRecommendation] = None
    annotation: Annotation = field(default_factory=Annotation)
    status: Status = Status.DISCOVERED
    evidence_event_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "domain": self.domain,
            "description": self.description,
            "owner": self.annotation.owner or self.owner,
            "owner_role": self.annotation.owner_role or self.owner_role,
            "criteria": self.annotation.criteria or self.criteria,
            "input_data": self.input_data,
            "sources": self.sources,
            "actors": self.actors,
            "event_count": self.event_count,
            "signals": self.signals.to_dict(),
            "recommendation": self.recommendation.to_dict() if self.recommendation else None,
            "annotation": asdict(self.annotation),
            "status": self.status.value,
            "evidence_event_ids": self.evidence_event_ids[:25],
        }


@dataclass
class Domain:
    name: str
    decisions: list[Decision] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "decision_count": len(self.decisions),
            "decisions": [d.to_dict() for d in self.decisions],
        }


# ---------------------------------------------------------------------------
# Small numeric helpers shared across the engine
# ---------------------------------------------------------------------------


def log_scale(count: int, full_at: int = 1000) -> float:
    """Map a count to 0..1 on a log scale, saturating near ``full_at``."""
    if count <= 0:
        return 0.0
    return min(1.0, math.log10(count + 1) / math.log10(full_at + 1))
