"""Rung lifecycle state machine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from ..models import (
    Agent,
    AgentStatus,
    ApprovalDecision,
    AuditOutcome,
    ChangeDirection,
    RungAssignment,
    RungChangeRequest,
    WorkflowStatus,
    _now,
    _ts,
    _uid,
)
from .approval import apply_decision, build_approval_steps, resolve_chain

_hooks: list[Callable[[str, dict[str, Any]], None]] = []


def register_lifecycle_hook(fn: Callable[[str, dict[str, Any]], None]) -> None:
    _hooks.append(fn)


def _emit(event: str, data: dict[str, Any]) -> None:
    for fn in _hooks:
        try:
            fn(event, data)
        except Exception:
            pass


class LifecycleEngine:
    def __init__(
        self,
        agents: dict[str, Agent],
        requests: dict[str, RungChangeRequest],
        assignments: dict[str, RungAssignment],
        on_change: Optional[Callable[[Agent, RungAssignment], None]] = None,
    ) -> None:
        self._agents = agents
        self._requests = requests
        self._assignments = assignments
        self._on_change = on_change

    def register_agent(self, name: str, owner: str, owner_email: str = "",
                       description: str = "", initial_rung: int = 0,
                       tags: dict[str, str] | None = None) -> Agent:
        agent = Agent(
            id=_uid("agt_"),
            name=name,
            description=description,
            owner=owner,
            owner_email=owner_email,
            current_rung=initial_rung,
            tags=tags or {},
        )
        assignment = RungAssignment(
            id=_uid("asgn_"),
            agent_id=agent.id,
            rung=initial_rung,
            granted_by="system",
            workflow_id=None,
        )
        agent.current_assignment_id = assignment.id
        self._agents[agent.id] = agent
        self._assignments[assignment.id] = assignment
        _emit("agent_registered", {"agent": agent.to_dict()})
        return agent

    def submit_change_request(
        self,
        agent_id: str,
        to_rung: int,
        requested_by: str,
        justification: str,
        direction: Optional[ChangeDirection] = None,
    ) -> RungChangeRequest:
        agent = self._agents[agent_id]
        from_rung = agent.current_rung

        if direction is None:
            if to_rung == 0 and from_rung > 0:
                direction = ChangeDirection.SUSPENSION
            elif to_rung > from_rung:
                direction = ChangeDirection.PROMOTION
            elif to_rung < from_rung:
                direction = ChangeDirection.DEMOTION
            else:
                raise ValueError(f"Agent is already at rung {from_rung}.")

        chain = resolve_chain(direction, from_rung, to_rung)
        steps = build_approval_steps(chain)
        expires_at = (_now() + timedelta(hours=chain.approval_window_hours)).isoformat()

        if direction in (ChangeDirection.DEMOTION, ChangeDirection.SUSPENSION):
            for step in steps:
                if step.approver_role in ("ciso", "ai_governance_officer"):
                    step.decision = ApprovalDecision.APPROVED
                    step.decided_at = _ts()
                    step.notes = "Auto-approved: requester holds governance role."

        req = RungChangeRequest(
            id=_uid("wcr_"),
            agent_id=agent_id,
            direction=direction,
            from_rung=from_rung,
            to_rung=to_rung,
            requested_by=requested_by,
            justification=justification,
            approval_steps=steps,
            expires_at=expires_at,
        )

        if req.is_fully_approved():
            req.status = WorkflowStatus.APPROVED

        self._requests[req.id] = req
        _emit("change_request_submitted", {"request": req.to_dict()})
        return req

    def approve_step(self, request_id: str, approver: str,
                     approver_role: str, notes: str = "") -> RungChangeRequest:
        req = self._get_pending_request(request_id)
        step = apply_decision(req, approver, approver_role,
                              ApprovalDecision.APPROVED, notes)
        if step is None:
            raise ValueError(f"No pending step for role '{approver_role}' "
                             f"in request {request_id}.")
        if req.is_fully_approved():
            req.status = WorkflowStatus.APPROVED
        _emit("step_approved", {"request_id": request_id, "approver": approver})
        return req

    def reject_step(self, request_id: str, approver: str,
                    approver_role: str, notes: str = "") -> RungChangeRequest:
        req = self._get_pending_request(request_id)
        step = apply_decision(req, approver, approver_role,
                              ApprovalDecision.REJECTED, notes)
        if step is None:
            raise ValueError(f"No pending step for role '{approver_role}'.")
        req.status = WorkflowStatus.REJECTED
        _emit("step_rejected", {"request_id": request_id, "approver": approver})
        return req

    def cancel_request(self, request_id: str, cancelled_by: str) -> RungChangeRequest:
        req = self._requests[request_id]
        if req.status != WorkflowStatus.PENDING:
            raise ValueError(f"Request {request_id} is not pending.")
        req.status = WorkflowStatus.CANCELLED
        _emit("request_cancelled", {"request_id": request_id, "by": cancelled_by})
        return req

    def expire_stale_requests(self) -> list[str]:
        expired = []
        for req in self._requests.values():
            if req.status == WorkflowStatus.PENDING and req.is_expired():
                req.status = WorkflowStatus.EXPIRED
                expired.append(req.id)
                _emit("request_expired", {"request_id": req.id})
        return expired

    def execute_change(self, request_id: str) -> tuple[Agent, RungAssignment]:
        req = self._requests[request_id]
        if req.status != WorkflowStatus.APPROVED:
            raise ValueError(f"Request {request_id} is not approved "
                             f"(status: {req.status.value}).")

        agent = self._agents[req.agent_id]

        if agent.current_assignment_id:
            old = self._assignments.get(agent.current_assignment_id)
            if old:
                old.revoked_at = _ts()
                old.revocation_reason = (
                    f"Rung changed from {req.from_rung} to {req.to_rung} "
                    f"via request {req.id}."
                )

        new_assignment = RungAssignment(
            id=_uid("asgn_"),
            agent_id=agent.id,
            rung=req.to_rung,
            granted_by=req.requested_by,
            workflow_id=req.id,
        )
        self._assignments[new_assignment.id] = new_assignment

        prev_status = agent.status
        agent.current_rung = req.to_rung
        agent.current_assignment_id = new_assignment.id
        agent.last_rung_change_at = _ts()
        if req.direction == ChangeDirection.SUSPENSION:
            agent.status = AgentStatus.SUSPENDED
        elif prev_status == AgentStatus.SUSPENDED and req.to_rung > 0:
            agent.status = AgentStatus.ACTIVE

        req.status = WorkflowStatus.EXECUTED
        req.executed_at = _ts()
        req.new_assignment_id = new_assignment.id

        _emit("rung_changed", {
            "agent_id": agent.id,
            "from_rung": req.from_rung,
            "to_rung": req.to_rung,
            "assignment_id": new_assignment.id,
            "direction": req.direction.value,
        })

        if self._on_change:
            self._on_change(agent, new_assignment)

        return agent, new_assignment

    def _get_pending_request(self, request_id: str) -> RungChangeRequest:
        req = self._requests[request_id]
        if req.is_expired():
            req.status = WorkflowStatus.EXPIRED
            raise ValueError(f"Request {request_id} has expired.")
        if req.status != WorkflowStatus.PENDING:
            raise ValueError(f"Request {request_id} is not pending "
                             f"(status: {req.status.value}).")
        return req

    def list_pending(self) -> list[RungChangeRequest]:
        return [r for r in self._requests.values()
                if r.status == WorkflowStatus.PENDING]

    def get_agent_history(self, agent_id: str) -> list[RungAssignment]:
        return sorted(
            [a for a in self._assignments.values() if a.agent_id == agent_id],
            key=lambda a: a.granted_at,
        )
