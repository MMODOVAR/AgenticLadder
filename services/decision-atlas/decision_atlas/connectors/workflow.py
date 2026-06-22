"""Workflow / BPM connector (Airflow, Temporal, Camunda, Step Functions-shaped).

Reads workflow execution traces and emits a DecisionEvent for each task whose
type indicates a branch/gateway/human-task — i.e. a point where the workflow
*decides*. Gateways and exclusive branches are the automatable decisions an
agentic transformation cares about.
"""
from __future__ import annotations

from typing import Any

from ..models import DecisionEvent
from .base import Connector, register_connector
from ._util import as_bool, load_records, parse_ts

DECISION_TASK_TYPES = {"gateway", "decision", "branch", "choice",
                       "human_task", "approval", "exclusive_gateway"}


@register_connector("workflow")
class WorkflowConnector(Connector):
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
        for run in self._load():
            wf = run.get("workflow") or run.get("name") or "workflow"
            domain = run.get("domain") or wf
            run_id = run.get("run_id") or run.get("id") or "run"
            for i, task in enumerate(run.get("tasks") or []):
                ttype = (task.get("type") or "").lower()
                if ttype not in DECISION_TASK_TYPES:
                    continue
                task_name = task.get("name") or task.get("id") or f"task{i}"
                events.append(self._new_event(
                    id=f"{run_id}:{task_name}:{i}",
                    decision_key=f"{wf}.{task_name}".lower().replace(" ", "_"),
                    timestamp=parse_ts(task.get("completed_at") or task.get("timestamp")),
                    actor=task.get("assignee") or task.get("by") or "system",
                    role=task.get("role"),
                    action=task.get("decision") or task.get("branch") or "decided",
                    outcome=task.get("decision") or task.get("branch") or task.get("result"),
                    domain=domain,
                    input_fields=sorted((task.get("inputs") or {}).keys())
                    if isinstance(task.get("inputs"), dict)
                    else [str(x) for x in (task.get("inputs") or [])],
                    reversible=as_bool(task.get("reversible")),
                    overturned=as_bool(task.get("overturned")),
                    impact=task.get("impact"),
                    raw=task,
                ))
        return events
