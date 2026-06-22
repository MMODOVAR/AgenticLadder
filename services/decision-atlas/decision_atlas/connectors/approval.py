"""Approval-chain connector (ServiceNow / generic ITSM-shaped).

Reads approval records — change requests, access grants, purchase approvals — and
emits one DecisionEvent per approval step. Captures the approve/reject outcome
and whether the request was later reversed, which feeds the historical-consistency
signal directly.
"""
from __future__ import annotations

from typing import Any

from ..models import DecisionEvent
from .base import Connector, register_connector
from ._util import as_bool, load_records, parse_ts

REGULATED_HINT = {"sox", "gdpr", "hipaa", "pci", "compliance", "audit", "legal"}


@register_connector("approval")
class ApprovalConnector(Connector):
    def __init__(self, path: str, records: list[dict[str, Any]] | None = None,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.path = path
        self._records = records

    def _load(self) -> list[dict[str, Any]]:
        if self._records is not None:
            return self._records
        return load_records(self.path)

    def fetch_events(self) -> list[DecisionEvent]:
        events: list[DecisionEvent] = []
        for rec in self._load():
            category = (rec.get("category") or rec.get("type") or "approval").lower()
            domain = rec.get("domain") or rec.get("department") or "Operations"
            decision_key = f"{category}.approval"

            amount = rec.get("amount") or rec.get("value")
            impact = rec.get("impact")
            if impact is None and isinstance(amount, (int, float)):
                # Map monetary value to 0..1 with $250k as "high".
                impact = min(1.0, float(amount) / 250_000.0)

            decision = (rec.get("decision") or rec.get("state")
                        or rec.get("outcome") or "approved").lower()

            inputs = rec.get("inputs")
            if isinstance(inputs, dict):
                input_fields = sorted(inputs.keys())
            elif isinstance(inputs, list):
                input_fields = [str(x) for x in inputs]
            else:
                input_fields = sorted(
                    k for k in rec.keys()
                    if k not in ("decision", "state", "outcome", "approver")
                )

            events.append(self._new_event(
                id=str(rec.get("id") or rec.get("number") or len(events)),
                decision_key=decision_key,
                timestamp=parse_ts(rec.get("approved_at") or rec.get("timestamp")),
                actor=rec.get("approver") or rec.get("actor"),
                role=rec.get("approver_role") or rec.get("role"),
                action=decision,
                outcome=decision,
                domain=domain,
                input_fields=input_fields,
                reversible=as_bool(rec.get("reversible")),
                overturned=as_bool(rec.get("overturned") or rec.get("reversed")),
                impact=float(impact) if impact is not None else None,
                raw=rec,
            ))
        return events
