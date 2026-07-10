"""Built-in blast-radius containment policies per autonomy rung."""
from __future__ import annotations

from ..models import ActionCategory, RungPolicy

RUNG_POLICIES: dict[int, RungPolicy] = {

    0: RungPolicy(
        rung=0,
        allowed_actions=set(),
        denied_actions=set(ActionCategory),
        require_approval_actions=set(),
        rate_limits={},
        max_financial_amount=0.0,
        rollback_window_seconds=None,
        credential_ttl_seconds=None,
        description=(
            "No agent credentials. All actions are performed by humans. "
            "Agent may only be registered and queued for promotion."
        ),
    ),

    1: RungPolicy(
        rung=1,
        allowed_actions={ActionCategory.READ},
        denied_actions={
            ActionCategory.WRITE, ActionCategory.DELETE, ActionCategory.EXECUTE,
            ActionCategory.DEPLOY, ActionCategory.FINANCIAL,
            ActionCategory.ACCESS_CONTROL, ActionCategory.COMMUNICATE,
            ActionCategory.IRREVERSIBLE,
        },
        require_approval_actions=set(),
        rate_limits={"read": 200},
        max_financial_amount=0.0,
        rollback_window_seconds=None,
        credential_ttl_seconds=3600,
        description=(
            "Read-only access. Agent surfaces data and context; humans decide. "
            "No write, execute, or communication operations permitted."
        ),
    ),

    2: RungPolicy(
        rung=2,
        allowed_actions={ActionCategory.READ, ActionCategory.WRITE},
        denied_actions={
            ActionCategory.DELETE, ActionCategory.EXECUTE, ActionCategory.DEPLOY,
            ActionCategory.FINANCIAL, ActionCategory.ACCESS_CONTROL,
            ActionCategory.IRREVERSIBLE,
        },
        require_approval_actions={ActionCategory.COMMUNICATE},
        rate_limits={"read": 500, "write": 50},
        max_financial_amount=0.0,
        rollback_window_seconds=1800,
        credential_ttl_seconds=7200,
        description=(
            "Agent proposes actions; a human approves before any execution. "
            "Write operations create drafts/proposals only, not live changes. "
            "External communications require human approval."
        ),
    ),

    3: RungPolicy(
        rung=3,
        allowed_actions={
            ActionCategory.READ, ActionCategory.WRITE,
            ActionCategory.COMMUNICATE,
        },
        denied_actions={
            ActionCategory.IRREVERSIBLE, ActionCategory.ACCESS_CONTROL,
        },
        require_approval_actions={
            ActionCategory.DELETE, ActionCategory.EXECUTE,
            ActionCategory.DEPLOY, ActionCategory.FINANCIAL,
        },
        rate_limits={"read": 1000, "write": 100, "execute": 20, "financial": 5},
        max_financial_amount=1000.0,
        rollback_window_seconds=3600,
        credential_ttl_seconds=14400,
        description=(
            "Agent executes reversible actions; humans review after the fact. "
            "Delete, deploy, execute, and financial actions require co-sign. "
            "Irreversible and access-control actions always denied. "
            "Max $1,000 per financial action; 1-hour rollback window."
        ),
    ),

    4: RungPolicy(
        rung=4,
        allowed_actions={
            ActionCategory.READ, ActionCategory.WRITE, ActionCategory.DELETE,
            ActionCategory.EXECUTE, ActionCategory.DEPLOY,
            ActionCategory.COMMUNICATE, ActionCategory.FINANCIAL,
        },
        denied_actions={ActionCategory.IRREVERSIBLE},
        require_approval_actions={ActionCategory.ACCESS_CONTROL},
        rate_limits={"read": 5000, "write": 500, "execute": 100,
                     "deploy": 10, "financial": 20},
        max_financial_amount=50000.0,
        rollback_window_seconds=7200,
        credential_ttl_seconds=28800,
        description=(
            "Agent executes within guardrails. Most actions auto-approved; "
            "access-control changes require human approval. "
            "Irreversible actions always denied. "
            "Max $50,000 per financial action; circuit-breaker on anomaly."
        ),
    ),

    5: RungPolicy(
        rung=5,
        allowed_actions=set(ActionCategory),
        denied_actions=set(),
        require_approval_actions=set(),
        rate_limits={"execute": 500, "deploy": 50, "financial": 100},
        max_financial_amount=None,
        rollback_window_seconds=None,
        credential_ttl_seconds=86400,
        description=(
            "Full autonomy. Agent owns all decisions including edge cases. "
            "Humans monitor KPIs and anomaly dashboards only. "
            "Circuit-breaker auto-demotes on sustained anomaly. "
            "All credentials are rotated on any governance change."
        ),
    ),
}


def get_policy(rung: int) -> RungPolicy:
    rung = max(0, min(5, int(rung)))
    return RUNG_POLICIES[rung]


def all_policies() -> list[RungPolicy]:
    return [RUNG_POLICIES[r] for r in sorted(RUNG_POLICIES)]
