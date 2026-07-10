"""RungGuard control-plane store.

Wires together the lifecycle engine, credential manager, policy engine, and
audit log into a single cohesive control plane. Thread-safe via RLock.
"""
from __future__ import annotations

import threading
from typing import Any, Optional

from ..audit.log import AuditLog
from ..credentials.manager import CredentialManager
from ..lifecycle.engine import LifecycleEngine, register_lifecycle_hook
from ..models import (
    ActionCategory,
    Agent,
    AuditOutcome,
    ChangeDirection,
    PolicyEvaluation,
    RungAssignment,
    RungChangeRequest,
    RungCredential,
    WorkflowStatus,
)
from ..policies.engine import evaluate as policy_evaluate
from ..policies.rules import all_policies


class ControlPlane:
    def __init__(self) -> None:
        self._lock = threading.RLock()

        self._agents: dict[str, Agent] = {}
        self._requests: dict[str, RungChangeRequest] = {}
        self._assignments: dict[str, RungAssignment] = {}
        self._credentials: dict[str, RungCredential] = {}

        self.audit = AuditLog()
        self.cred_manager = CredentialManager(self._credentials)

        self.lifecycle = LifecycleEngine(
            agents=self._agents,
            requests=self._requests,
            assignments=self._assignments,
            on_change=self._on_rung_change,
        )

        register_lifecycle_hook(self._lifecycle_hook)

    def _on_rung_change(self, agent: Agent, new_assignment: RungAssignment) -> None:
        self.cred_manager.on_rung_change(agent, new_assignment)
        self.audit.record_rung_change(
            agent_id=agent.id,
            from_rung=new_assignment.rung,
            to_rung=agent.current_rung,
            assignment_id=new_assignment.id,
            requested_by=new_assignment.granted_by,
            direction="change",
            workflow_id=new_assignment.workflow_id or "",
        )

    def _lifecycle_hook(self, event: str, data: dict[str, Any]) -> None:
        if event == "rung_changed":
            agent_id = data.get("agent_id", "")
            assignment_id = data.get("assignment_id", "")
            self.audit.record_rung_change(
                agent_id=agent_id,
                from_rung=data.get("from_rung", 0),
                to_rung=data.get("to_rung", 0),
                assignment_id=assignment_id,
                requested_by="lifecycle_engine",
                direction=data.get("direction", "change"),
            )

    def register_agent(self, name: str, owner: str, owner_email: str = "",
                       description: str = "", tags: dict[str, str] | None = None,
                       initial_rung: int = 0) -> Agent:
        with self._lock:
            agent = self.lifecycle.register_agent(
                name=name, owner=owner, owner_email=owner_email,
                description=description, initial_rung=initial_rung,
                tags=tags,
            )
            return agent

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())

    def submit_change_request(self, agent_id: str, to_rung: int,
                              requested_by: str, justification: str,
                              direction: Optional[ChangeDirection] = None) -> RungChangeRequest:
        with self._lock:
            return self.lifecycle.submit_change_request(
                agent_id=agent_id, to_rung=to_rung,
                requested_by=requested_by, justification=justification,
                direction=direction,
            )

    def approve_step(self, request_id: str, approver: str,
                     approver_role: str, notes: str = "") -> RungChangeRequest:
        with self._lock:
            req = self.lifecycle.approve_step(request_id, approver, approver_role, notes)
            if req.status == WorkflowStatus.APPROVED:
                self.lifecycle.execute_change(request_id)
            return req

    def reject_step(self, request_id: str, approver: str,
                    approver_role: str, notes: str = "") -> RungChangeRequest:
        with self._lock:
            return self.lifecycle.reject_step(request_id, approver, approver_role, notes)

    def cancel_request(self, request_id: str,
                       cancelled_by: str) -> RungChangeRequest:
        with self._lock:
            return self.lifecycle.cancel_request(request_id, cancelled_by)

    def list_requests(self, status: Optional[str] = None) -> list[RungChangeRequest]:
        reqs = list(self._requests.values())
        if status:
            reqs = [r for r in reqs if r.status.value == status]
        return sorted(reqs, key=lambda r: r.requested_at, reverse=True)

    def check_action(self, agent_id: str, action: str,
                     context: dict[str, Any] | None = None) -> PolicyEvaluation:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent is None:
                raise KeyError(f"Agent not found: {agent_id}")
            assignment_id = agent.current_assignment_id or ""
            result = policy_evaluate(
                agent_id=agent_id,
                assignment_id=assignment_id,
                rung=agent.current_rung,
                action=action,
                context=context or {},
            )
            outcome = (AuditOutcome.ALLOWED if result.outcome.value == "allow"
                       else AuditOutcome.DENIED if result.outcome.value == "deny"
                       else AuditOutcome.ESCALATED if result.outcome.value == "escalate"
                       else AuditOutcome.RATE_LIMITED if result.outcome.value == "rate_limit"
                       else AuditOutcome.APPROVAL_REQUIRED)
            active_creds = self.cred_manager.active_for_agent(agent_id)
            cred_id = active_creds[0].id if active_creds else None
            self.audit.record_action(
                evaluation=result,
                actual_outcome=outcome,
                credential_id=cred_id,
            )
            return result

    def summary(self) -> dict[str, Any]:
        agents = list(self._agents.values())
        creds = list(self._credentials.values())
        pending = [r for r in self._requests.values()
                   if r.status == WorkflowStatus.PENDING]
        rung_dist: dict[int, int] = {}
        for a in agents:
            rung_dist[a.current_rung] = rung_dist.get(a.current_rung, 0) + 1
        return {
            "agents": {
                "total": len(agents),
                "active": sum(1 for a in agents if a.status.value == "active"),
                "suspended": sum(1 for a in agents if a.status.value == "suspended"),
                "rung_distribution": {str(k): rung_dist[k] for k in sorted(rung_dist)},
            },
            "pending_approvals": len(pending),
            "credentials": self.cred_manager.summary(),
            "audit": self.audit.stats(),
        }

    def policies(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in all_policies()]
