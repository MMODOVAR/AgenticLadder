"""Ticketing connector (Jira-shaped).

Reads issues with a changelog/transition history and emits a DecisionEvent for
each meaningful state transition — the moments where someone *decided* to move
work forward. The decision_key is derived from project + issue type + the target
status so that, e.g., every "Move to Approved" across thousands of refund
tickets clusters into one decision.

Although named for Jira, the same shape covers most ticketing tools (GitHub
Issues, Azure DevOps, Linear) by adjusting the field names in the spec — or fall
back to the universal ``audit_log`` connector.
"""
from __future__ import annotations

from typing import Any

from ..models import DecisionEvent
from .base import Connector, register_connector
from ._util import as_bool, load_records, parse_ts

# Statuses that represent a real decision point rather than mechanical movement.
DECISION_STATUSES = {
    "approved", "rejected", "declined", "done", "resolved", "closed",
    "escalated", "cancelled", "canceled", "denied", "granted",
}

# Statuses we treat as "later reversed" when a ticket bounces back.
REOPEN_STATUSES = {"reopened", "in progress", "to do", "open", "backlog"}


@register_connector("jira")
class JiraConnector(Connector):
    def __init__(self, path: str = "", records: list[dict[str, Any]] | None = None,
                 decision_statuses: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.path = path
        self._records = records
        self.decision_statuses = {
            s.lower() for s in (decision_statuses or DECISION_STATUSES)
        }

    def _load(self) -> list[dict[str, Any]]:
        if self._records is not None:
            return self._records
        if not self.path:
            raise ValueError(f"Connector '{self.name}': provide 'path' or inline 'records'.")
        return load_records(self.path)

    def fetch_events(self) -> list[DecisionEvent]:
        events: list[DecisionEvent] = []
        for issue in self._load():
            key = issue.get("key", "ISSUE")
            project = issue.get("project") or key.split("-")[0]
            issue_type = (issue.get("type") or issue.get("issuetype") or "task")
            domain = issue.get("domain") or project
            fields = sorted(
                k for k in (issue.get("fields") or {}).keys()
            )
            priority = (issue.get("priority") or "").lower()
            impact = {"blocker": 0.95, "critical": 0.9, "highest": 0.85,
                      "high": 0.7, "medium": 0.5, "low": 0.3,
                      "lowest": 0.2}.get(priority)

            transitions = issue.get("transitions") or issue.get("changelog") or []
            reopened_later = any(
                (t.get("to") or t.get("status") or "").lower() in REOPEN_STATUSES
                for t in transitions
            )
            for i, t in enumerate(transitions):
                to_status = (t.get("to") or t.get("status") or "").lower()
                if to_status not in self.decision_statuses:
                    continue
                # Was this terminal decision overturned by a later reopen?
                overturned = any(
                    (later.get("to") or later.get("status") or "").lower()
                    in REOPEN_STATUSES
                    for later in transitions[i + 1:]
                )
                events.append(self._new_event(
                    id=f"{key}:{i}",
                    decision_key=f"{project}.{issue_type}.{to_status}".lower(),
                    timestamp=parse_ts(t.get("when") or t.get("timestamp")),
                    actor=t.get("by") or t.get("author"),
                    role=t.get("role"),
                    action=to_status,
                    outcome=to_status,
                    domain=domain,
                    input_fields=fields,
                    reversible=as_bool(t.get("reversible")) if t.get("reversible") is not None else reopened_later,
                    overturned=overturned,
                    impact=impact,
                    raw={"issue": key, "transition": t},
                ))
        return events
