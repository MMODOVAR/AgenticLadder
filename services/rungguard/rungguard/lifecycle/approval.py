"""Approval chain definitions and routing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import (
    ApprovalDecision,
    ApprovalStep,
    ChangeDirection,
    RungChangeRequest,
    _uid,
    _ts,
)


@dataclass
class ApprovalChainDef:
    direction: ChangeDirection
    min_from_rung: int
    min_to_rung: int
    approver_roles: list[str]
    parallel: bool = False
    approval_window_hours: int = 48
    description: str = ""

    def matches(self, direction: ChangeDirection, from_rung: int, to_rung: int) -> bool:
        return (
            self.direction == direction
            and from_rung >= self.min_from_rung
            and to_rung >= self.min_to_rung
        )


_CHAINS: list[ApprovalChainDef] = [
    ApprovalChainDef(
        direction=ChangeDirection.SUSPENSION,
        min_from_rung=0, min_to_rung=0,
        approver_roles=["ciso"],
        parallel=False, approval_window_hours=1,
        description="Suspension requires CISO approval; 1-hour window.",
    ),
    ApprovalChainDef(
        direction=ChangeDirection.DEMOTION,
        min_from_rung=0, min_to_rung=0,
        approver_roles=["ai_governance_officer"],
        parallel=False, approval_window_hours=4,
        description="Demotions are single-approver fast-track.",
    ),
    ApprovalChainDef(
        direction=ChangeDirection.REINSTATEMENT,
        min_from_rung=0, min_to_rung=0,
        approver_roles=["ai_governance_officer", "ciso"],
        parallel=True, approval_window_hours=24,
        description="Reinstatement after suspension needs dual approval.",
    ),
    ApprovalChainDef(
        direction=ChangeDirection.PROMOTION,
        min_from_rung=4, min_to_rung=5,
        approver_roles=["domain_owner", "ai_governance_officer", "ciso"],
        parallel=True, approval_window_hours=72,
        description="Full autonomy promotion requires domain owner + AI governance + CISO.",
    ),
    ApprovalChainDef(
        direction=ChangeDirection.PROMOTION,
        min_from_rung=3, min_to_rung=4,
        approver_roles=["domain_owner", "ai_governance_officer"],
        parallel=True, approval_window_hours=48,
        description="Conditional autonomy promotion needs domain owner + AI governance.",
    ),
    ApprovalChainDef(
        direction=ChangeDirection.PROMOTION,
        min_from_rung=0, min_to_rung=3,
        approver_roles=["domain_owner"],
        parallel=False, approval_window_hours=48,
        description="Supervised promotion needs domain owner sign-off.",
    ),
    ApprovalChainDef(
        direction=ChangeDirection.PROMOTION,
        min_from_rung=0, min_to_rung=0,
        approver_roles=["team_lead"],
        parallel=False, approval_window_hours=24,
        description="Lower-rung promotions need team lead sign-off.",
    ),
]


def register_chain(chain: ApprovalChainDef) -> None:
    _CHAINS.insert(0, chain)


def resolve_chain(direction: ChangeDirection, from_rung: int,
                  to_rung: int) -> ApprovalChainDef:
    for chain in _CHAINS:
        if chain.matches(direction, from_rung, to_rung):
            return chain
    return ApprovalChainDef(
        direction=direction,
        min_from_rung=0, min_to_rung=0,
        approver_roles=["team_lead"],
        description="Default approval chain.",
    )


def build_approval_steps(chain: ApprovalChainDef) -> list[ApprovalStep]:
    return [
        ApprovalStep(
            id=_uid("step_"),
            approver=role,
            approver_role=role,
        )
        for role in chain.approver_roles
    ]


def apply_decision(request: RungChangeRequest, approver: str, approver_role: str,
                   decision: ApprovalDecision, notes: str = "") -> ApprovalStep | None:
    for step in request.approval_steps:
        if step.decision != ApprovalDecision.PENDING:
            continue
        if step.approver_role == approver_role or step.approver == approver:
            step.decision = decision
            step.decided_at = _ts()
            step.notes = notes
            return step
    return None
