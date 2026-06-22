"""In-memory atlas store with optional JSON persistence.

Holds the discovered decision map and applies owner annotations/approvals,
re-running the rung engine whenever an owner overrides a signal or sets a target.
Swappable for a database in production — the API only depends on this interface.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from ..models import Decision, DecisionSignals, Domain, Provenance, Signal, Status
from ..rung.engine import recommend


class AtlasStore:
    def __init__(self) -> None:
        self._domains: dict[str, Domain] = {}
        self._decisions: dict[str, Decision] = {}
        self._lock = threading.RLock()

    # --- population ---------------------------------------------------------

    def load_domains(self, domains: list[Domain]) -> None:
        with self._lock:
            self._domains = {d.name: d for d in domains}
            self._decisions = {
                dec.id: dec for d in domains for dec in d.decisions
            }

    # --- reads --------------------------------------------------------------

    def domains(self) -> list[Domain]:
        with self._lock:
            return list(self._domains.values())

    def get_domain(self, name: str) -> Optional[Domain]:
        return self._domains.get(name)

    def get_decision(self, decision_id: str) -> Optional[Decision]:
        return self._decisions.get(decision_id)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            decisions = list(self._decisions.values())
            by_rung: dict[int, int] = {}
            for d in decisions:
                if d.recommendation:
                    r = d.recommendation.recommended_rung
                    by_rung[r] = by_rung.get(r, 0) + 1
            return {
                "domain_count": len(self._domains),
                "decision_count": len(decisions),
                "approved": sum(1 for d in decisions if d.status == Status.APPROVED),
                "annotated": sum(1 for d in decisions if d.status == Status.ANNOTATED),
                "discovered": sum(1 for d in decisions if d.status == Status.DISCOVERED),
                "recommended_rung_histogram": {
                    str(k): by_rung[k] for k in sorted(by_rung)
                },
            }

    # --- writes -------------------------------------------------------------

    def annotate(self, decision_id: str, patch: dict[str, Any]) -> Decision:
        with self._lock:
            dec = self._decisions[decision_id]
            ann = dec.annotation
            for field_name in ("owner", "owner_role", "criteria", "notes"):
                if field_name in patch and patch[field_name] is not None:
                    setattr(ann, field_name, patch[field_name])

            overrides = patch.get("signal_overrides")
            if overrides:
                ann.signal_overrides.update(
                    {k: float(v) for k, v in overrides.items()}
                )
                _apply_signal_overrides(dec.signals, ann.signal_overrides)

            if "target_rung_override" in patch:
                ann.target_rung_override = (
                    None if patch["target_rung_override"] is None
                    else int(patch["target_rung_override"])
                )

            # Recompute the recommendation with overrides applied.
            dec.recommendation = recommend(
                dec.signals,
                event_count=dec.event_count,
                target_override=ann.target_rung_override,
            )
            if dec.status == Status.DISCOVERED:
                dec.status = Status.ANNOTATED
            return dec

    def approve(self, decision_id: str, approved_by: str) -> Decision:
        with self._lock:
            dec = self._decisions[decision_id]
            dec.status = Status.APPROVED
            dec.annotation.approved_by = approved_by
            dec.annotation.approved_at = datetime.now(timezone.utc).isoformat()
            return dec

    # --- persistence --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"domains": [d.to_dict() for d in self.domains()]}

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)


def _apply_signal_overrides(signals: DecisionSignals,
                            overrides: dict[str, float]) -> None:
    smap = signals.as_map()
    for name, value in overrides.items():
        if name in smap:
            setattr(signals, name, Signal(
                float(value), Provenance.ANNOTATED, "set by owner"
            ).clamp())
