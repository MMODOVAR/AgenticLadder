"""Rung-tagged audit log."""
from __future__ import annotations

import json
from collections import deque
from typing import Any, Callable, Optional

from ..models import (
    ActionCategory,
    AuditEntry,
    AuditOutcome,
    PolicyEvaluation,
    PolicyOutcome,
    _uid,
    _ts,
)

MAX_IN_MEMORY = 10_000

_writers: list[Callable[[dict[str, Any]], None]] = []


def register_writer(fn: Callable[[dict[str, Any]], None]) -> None:
    _writers.append(fn)


class AuditLog:
    def __init__(self, max_entries: int = MAX_IN_MEMORY) -> None:
        self._entries: deque[AuditEntry] = deque(maxlen=max_entries)

    def record_action(
        self,
        evaluation: PolicyEvaluation,
        actual_outcome: AuditOutcome,
        source: str = "",
        target: str = "",
        credential_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            id=_uid("aud_"),
            agent_id=evaluation.agent_id,
            assignment_id=evaluation.assignment_id,
            rung_at_time=evaluation.rung,
            action=evaluation.action,
            action_category=evaluation.action_category.value,
            outcome=actual_outcome,
            policy_outcome=evaluation.outcome.value,
            timestamp=_ts(),
            source=source,
            target=target,
            context={**evaluation.context, **(context or {})},
            policy_evaluation_id=evaluation.id if hasattr(evaluation, "id") else None,
            credential_id=credential_id,
        )
        self._entries.append(entry)
        self._dispatch(entry)
        return entry

    def record_rung_change(
        self,
        agent_id: str,
        from_rung: int,
        to_rung: int,
        assignment_id: str,
        requested_by: str,
        direction: str,
        workflow_id: str = "",
    ) -> AuditEntry:
        entry = AuditEntry(
            id=_uid("aud_"),
            agent_id=agent_id,
            assignment_id=assignment_id,
            rung_at_time=to_rung,
            action=f"rung.{direction}",
            action_category="governance",
            outcome=AuditOutcome.ALLOWED,
            policy_outcome="allow",
            source="rungguard.lifecycle",
            target=f"rung:{to_rung}",
            context={
                "from_rung": from_rung,
                "to_rung": to_rung,
                "direction": direction,
                "requested_by": requested_by,
                "workflow_id": workflow_id,
            },
        )
        self._entries.append(entry)
        self._dispatch(entry)
        return entry

    def record_credential_event(
        self,
        agent_id: str,
        assignment_id: str,
        rung: int,
        event: str,
        credential_id: str,
        provider: str,
        reason: str = "",
    ) -> AuditEntry:
        entry = AuditEntry(
            id=_uid("aud_"),
            agent_id=agent_id,
            assignment_id=assignment_id,
            rung_at_time=rung,
            action=f"credential.{event}",
            action_category="credential",
            outcome=AuditOutcome.ALLOWED,
            policy_outcome="allow",
            source=f"rungguard.credentials.{provider}",
            target=credential_id,
            context={"event": event, "provider": provider, "reason": reason},
            credential_id=credential_id,
        )
        self._entries.append(entry)
        self._dispatch(entry)
        return entry

    def all(self) -> list[AuditEntry]:
        return list(self._entries)

    def for_agent(self, agent_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.agent_id == agent_id]

    def for_assignment(self, assignment_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.assignment_id == assignment_id]

    def denied(self) -> list[AuditEntry]:
        return [e for e in self._entries if e.outcome == AuditOutcome.DENIED]

    def recent(self, n: int = 50) -> list[AuditEntry]:
        entries = list(self._entries)
        return entries[-n:]

    def stats(self) -> dict[str, Any]:
        entries = list(self._entries)
        outcomes: dict[str, int] = {}
        by_rung: dict[int, int] = {}
        for e in entries:
            o = e.outcome.value if hasattr(e.outcome, "value") else str(e.outcome)
            outcomes[o] = outcomes.get(o, 0) + 1
            r = e.rung_at_time
            by_rung[r] = by_rung.get(r, 0) + 1
        return {
            "total_entries": len(entries),
            "by_outcome": outcomes,
            "by_rung": {str(k): by_rung[k] for k in sorted(by_rung)},
        }

    def export_jsonl(self) -> str:
        return "\n".join(
            json.dumps(e.to_dict(), default=str) for e in self._entries
        )

    def _dispatch(self, entry: AuditEntry) -> None:
        d = entry.to_dict()
        for fn in _writers:
            try:
                fn(d)
            except Exception:
                pass
