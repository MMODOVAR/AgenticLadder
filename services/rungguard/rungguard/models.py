"""Canonical, cloud-agnostic data model for RungGuard.

Every object in the control plane — agents, rung assignments, credentials,
change requests, policies, audit entries — is defined here. The rest of
the system (lifecycle engine, credential manager, policy evaluator, audit log,
API) operates purely on these types.

This module has zero runtime dependencies (pure standard library) so the
control plane core can be imported, tested, and embedded anywhere.
"""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"

def _ts(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    ACTIVE = "active"           # registered and operating within its rung
    SUSPENDED = "suspended"     # forcibly held at rung 0, no credentials
    DECOMMISSIONED = "decommissioned"  # removed from the registry

class WorkflowStatus(str, Enum):
    PENDING = "pending"         # awaiting all required approvals
    APPROVED = "approved"       # all approvers signed off — ready to execute
    REJECTED = "rejected"       # at least one approver rejected
    EXECUTED = "executed"       # rung change applied and credentials rotated
    CANCELLED = "cancelled"     # requester withdrew
    EXPIRED = "expired"         # approval window lapsed without decision

class ApprovalDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELEGATED = "delegated"     # passed to another approver

class CredentialStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"         # natural TTL elapsed
    REVOKED = "revoked"         # rung change triggered immediate revocation

class PolicyOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    RATE_LIMIT = "rate_limit"
    REQUIRE_APPROVAL = "require_approval"
    ESCALATE = "escalate"       # human must co-sign before execution

class ChangeDirection(str, Enum):
    PROMOTION = "promotion"     # rung goes up
    DEMOTION = "demotion"       # rung goes down (always fast-path approved by CISO+)
    SUSPENSION = "suspension"   # forced to rung 0
    REINSTATEMENT = "reinstatement"  # rung 0 → previous rung

class ActionCategory(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    DEPLOY = "deploy"
    FINANCIAL = "financial"
    ACCESS_CONTROL = "access_control"
    COMMUNICATE = "communicate"
    IRREVERSIBLE = "irreversible"

class AuditOutcome(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    ESCALATED = "escalated"
    RATE_LIMITED = "rate_limited"
    APPROVAL_REQUIRED = "approval_required"


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@dataclass
class Agent:
    """A registered autonomous agent in the RungGuard control plane."""
    id: str
    name: str
    description: str = ""
    owner: str = ""              # team / individual responsible
    owner_email: str = ""
    current_rung: int = 0
    status: AgentStatus = AgentStatus.ACTIVE
    registered_at: str = field(default_factory=_ts)
    last_rung_change_at: Optional[str] = None
    tags: dict[str, str] = field(default_factory=dict)
    # The assignment_id of the RungAssignment currently in effect.
    current_assignment_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ---------------------------------------------------------------------------
# Rung Assignment — the authoritative record of what rung an agent holds
# ---------------------------------------------------------------------------

@dataclass
class RungAssignment:
    """Immutable record of an agent holding a particular rung at a moment.

    Every credential and every audit entry references this ID, so you can
    always reconstruct *exactly* what an agent was authorized to do at the
    time it made any decision.
    """
    id: str
    agent_id: str
    rung: int
    granted_by: str              # user / system that authorized this assignment
    granted_at: str = field(default_factory=_ts)
    workflow_id: Optional[str] = None   # the change request that caused this
    revoked_at: Optional[str] = None
    revocation_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Rung Credential
# ---------------------------------------------------------------------------

@dataclass
class RungCredential:
    """A credential set issued for a specific rung assignment.

    The moment the assignment is superseded (rung change), the credential is
    revoked — immediately via the cloud provider, and status set to REVOKED.
    """
    id: str
    agent_id: str
    assignment_id: str
    rung: int
    provider: str                 # e.g. "env", "aws", "azure", "gcp", "vault", "k8s"
    credential_type: str          # e.g. "api_key", "iam_role", "service_account"
    # The actual secret — stored as opaque string; real systems point to provider references.
    secret_ref: str
    issued_at: str = field(default_factory=_ts)
    expires_at: Optional[str] = None
    status: CredentialStatus = CredentialStatus.ACTIVE
    revoked_at: Optional[str] = None
    revocation_reason: Optional[str] = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return _now().isoformat() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["is_expired"] = self.is_expired()
        return d


# ---------------------------------------------------------------------------
# Rung Change Request (promotion / demotion / suspension)
# ---------------------------------------------------------------------------

@dataclass
class ApprovalStep:
    """One approver's slot in the approval chain."""
    id: str
    approver: str                 # user or role
    approver_role: str = ""
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decided_at: Optional[str] = None
    notes: Optional[str] = None
    delegated_to: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decision"] = self.decision.value
        return d


@dataclass
class RungChangeRequest:
    """A governed workflow to promote or demote an agent's rung."""
    id: str
    agent_id: str
    direction: ChangeDirection
    from_rung: int
    to_rung: int
    requested_by: str
    justification: str
    requested_at: str = field(default_factory=_ts)
    status: WorkflowStatus = WorkflowStatus.PENDING
    approval_steps: list[ApprovalStep] = field(default_factory=list)
    executed_at: Optional[str] = None
    expires_at: Optional[str] = None   # approval window deadline
    # Result
    new_assignment_id: Optional[str] = None
    execution_notes: str = ""

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return _now().isoformat() >= self.expires_at

    def pending_approvers(self) -> list[str]:
        return [s.approver for s in self.approval_steps
                if s.decision == ApprovalDecision.PENDING]

    def is_fully_approved(self) -> bool:
        return all(s.decision == ApprovalDecision.APPROVED
                   for s in self.approval_steps)

    def is_rejected(self) -> bool:
        return any(s.decision == ApprovalDecision.REJECTED
                   for s in self.approval_steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "direction": self.direction.value,
            "from_rung": self.from_rung,
            "to_rung": self.to_rung,
            "requested_by": self.requested_by,
            "justification": self.justification,
            "requested_at": self.requested_at,
            "status": self.status.value,
            "approval_steps": [
                {
                    "id": s.id,
                    "approver": s.approver,
                    "approver_role": s.approver_role,
                    "decision": s.decision.value,
                    "decided_at": s.decided_at,
                    "notes": s.notes,
                }
                for s in self.approval_steps
            ],
            "executed_at": self.executed_at,
            "expires_at": self.expires_at,
            "new_assignment_id": self.new_assignment_id,
            "execution_notes": self.execution_notes,
            "pending_approvers": self.pending_approvers(),
        }


# ---------------------------------------------------------------------------
# Blast-radius containment policy per rung
# ---------------------------------------------------------------------------

@dataclass
class RungPolicy:
    """Per-rung containment policy that the policy engine enforces at action time."""
    rung: int
    allowed_actions: set[ActionCategory] = field(default_factory=set)
    denied_actions: set[ActionCategory] = field(default_factory=set)
    require_approval_actions: set[ActionCategory] = field(default_factory=set)
    rate_limits: dict[str, int] = field(default_factory=dict)
    max_financial_amount: Optional[float] = None
    rollback_window_seconds: Optional[int] = None
    credential_ttl_seconds: Optional[int] = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rung": self.rung,
            "allowed_actions": sorted(a.value for a in self.allowed_actions),
            "denied_actions": sorted(a.value for a in self.denied_actions),
            "require_approval_actions": sorted(a.value for a in self.require_approval_actions),
            "rate_limits": self.rate_limits,
            "max_financial_amount": self.max_financial_amount,
            "rollback_window_seconds": self.rollback_window_seconds,
            "credential_ttl_seconds": self.credential_ttl_seconds,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Policy evaluation result
# ---------------------------------------------------------------------------

@dataclass
class PolicyEvaluation:
    """Result of evaluating a proposed action against the agent's rung policy."""
    agent_id: str
    assignment_id: str
    rung: int
    action: str
    action_category: ActionCategory
    outcome: PolicyOutcome
    reason: str
    policy_rules_applied: list[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=_ts)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["outcome"] = self.outcome.value
        d["action_category"] = self.action_category.value
        return d


# ---------------------------------------------------------------------------
# Audit Entry — immutable, rung-tagged record of every decision/action
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """Immutable record of an agent action, tagged with the exact rung held."""
    id: str
    agent_id: str
    assignment_id: str
    rung_at_time: int
    action: str
    action_category: str
    outcome: AuditOutcome
    policy_outcome: str
    timestamp: str = field(default_factory=_ts)
    source: str = ""
    target: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    policy_evaluation_id: Optional[str] = None
    credential_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["outcome"] = self.outcome.value if isinstance(self.outcome, Enum) else self.outcome
        return d
