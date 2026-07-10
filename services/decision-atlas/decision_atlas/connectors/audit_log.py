"""Universal audit-log connector.

This is the workhorse that makes Decision Atlas cloud- and application-agnostic.
Point it at *any* structured log (JSON array or JSONL) — exported from AWS
CloudTrail, GCP Audit Logs, Azure Activity Log, a database table, an in-house
application event stream — and describe where the fields live via a ``mapping``.
No code change is needed to onboard a new system.

Example spec::

    {
      "type": "audit_log",
      "name": "cloudtrail-prod",
      "domain": "Platform",
      "path": "events.jsonl",
      "mapping": {
        "id": "eventID",
        "decision_key": "eventName",
        "timestamp": "eventTime",
        "actor": "userIdentity.arn",
        "action": "eventName",
        "outcome": "responseElements.status",
        "input_fields": "requestParameters",
        "domain": "recipientAccountId"
      }
    }
"""
from __future__ import annotations

import hashlib
from typing import Any

from ..models import DecisionEvent
from .base import Connector, register_connector
from ._util import as_bool, dig, first_str, listify, load_records, parse_ts

DEFAULT_MAPPING = {
    "id": "id",
    "decision_key": "decision",
    "timestamp": "timestamp",
    "actor": "actor",
    "role": "role",
    "action": "action",
    "outcome": "outcome",
    "domain": "domain",
    "input_fields": "inputs",
    "reversible": "reversible",
    "overturned": "overturned",
    "impact": "impact",
}


@register_connector("audit_log")
class AuditLogConnector(Connector):
    def __init__(self, path: str = "", mapping: dict[str, str] | None = None,
                 records: list[dict[str, Any]] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.path = path
        self.mapping = {**DEFAULT_MAPPING, **(mapping or {})}
        self._records = records  # allow in-memory injection (tests / API)

    def _load(self) -> list[dict[str, Any]]:
        if self._records is not None:
            return self._records
        if not self.path:
            raise ValueError(f"Connector '{self.name}': provide 'path' or inline 'records'.")
        return load_records(self.path)

    def fetch_events(self) -> list[DecisionEvent]:
        m = self.mapping
        events: list[DecisionEvent] = []
        for idx, rec in enumerate(self._load()):
            decision_key = first_str(dig(rec, m["decision_key"])) or "unknown.decision"
            raw_id = first_str(dig(rec, m["id"]))
            if not raw_id:
                raw_id = hashlib.sha1(
                    f"{self.name}:{idx}:{decision_key}".encode()
                ).hexdigest()[:12]

            inputs_val = dig(rec, m["input_fields"])
            if isinstance(inputs_val, dict):
                input_fields = sorted(inputs_val.keys())
            else:
                input_fields = listify(inputs_val)

            impact_val = dig(rec, m["impact"])
            try:
                impact = float(impact_val) if impact_val is not None else None
            except (TypeError, ValueError):
                impact = None

            events.append(self._new_event(
                id=str(raw_id),
                decision_key=str(decision_key),
                timestamp=parse_ts(dig(rec, m["timestamp"])),
                actor=first_str(dig(rec, m["actor"])),
                role=first_str(dig(rec, m["role"])),
                action=first_str(dig(rec, m["action"])),
                outcome=first_str(dig(rec, m["outcome"])),
                domain=first_str(dig(rec, m["domain"])),
                input_fields=input_fields,
                reversible=as_bool(dig(rec, m["reversible"])),
                overturned=as_bool(dig(rec, m["overturned"])),
                impact=impact,
                raw=rec,
            ))
        return events
