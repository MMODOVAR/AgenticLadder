"""Policy enforcement engine."""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from ..models import (
    ActionCategory,
    AuditOutcome,
    PolicyEvaluation,
    PolicyOutcome,
    RungPolicy,
    _uid,
    _ts,
)
from .rules import get_policy

_rate_counters: dict[str, dict[str, list[float]]] = defaultdict(
    lambda: defaultdict(list)
)


def _infer_category(action: str) -> ActionCategory:
    a = action.lower()
    if any(k in a for k in ("read", "get", "list", "describe", "query", "search",
                             "fetch", "retrieve", "show", "view")):
        return ActionCategory.READ
    if any(k in a for k in ("delete", "remove", "destroy", "purge", "drop")):
        return ActionCategory.DELETE
    if any(k in a for k in ("deploy", "release", "rollout", "rollback")):
        return ActionCategory.DEPLOY
    if any(k in a for k in ("pay", "charge", "refund", "transfer", "wire",
                             "disburse", "invoice", "financial", "payment")):
        return ActionCategory.FINANCIAL
    if any(k in a for k in ("grant", "revoke", "access", "iam", "role",
                             "permission", "policy", "rbac", "acl")):
        return ActionCategory.ACCESS_CONTROL
    if any(k in a for k in ("send", "email", "notify", "message", "slack",
                             "webhook", "communicate", "publish")):
        return ActionCategory.COMMUNICATE
    if any(k in a for k in ("irreversible", "permanent", "wipe", "terminate",
                             "shutdown", "delete_forever")):
        return ActionCategory.IRREVERSIBLE
    if any(k in a for k in ("run", "execute", "trigger", "invoke", "start",
                             "launch", "call")):
        return ActionCategory.EXECUTE
    if any(k in a for k in ("write", "create", "update", "put", "post",
                             "patch", "insert", "upsert", "save")):
        return ActionCategory.WRITE
    return ActionCategory.EXECUTE


def _check_rate_limit(agent_id: str, category: ActionCategory,
                      policy: RungPolicy) -> bool:
    key = category.value
    limit = policy.rate_limits.get(key)
    if limit is None:
        return True
    now = time.monotonic()
    window = 60.0
    timestamps = _rate_counters[agent_id][key]
    cutoff = now - window
    _rate_counters[agent_id][key] = [t for t in timestamps if t >= cutoff]
    if len(_rate_counters[agent_id][key]) >= limit:
        return False
    _rate_counters[agent_id][key].append(now)
    return True


def evaluate(
    agent_id: str,
    assignment_id: str,
    rung: int,
    action: str,
    context: dict[str, Any] | None = None,
    action_category: ActionCategory | None = None,
) -> PolicyEvaluation:
    context = context or {}
    policy = get_policy(rung)
    category = action_category or _infer_category(action)
    rules_applied: list[str] = []

    if category in policy.denied_actions:
        rules_applied.append(f"rung{rung}.deny: {category.value} actions are forbidden")
        return PolicyEvaluation(
            agent_id=agent_id,
            assignment_id=assignment_id,
            rung=rung,
            action=action,
            action_category=category,
            outcome=PolicyOutcome.DENY,
            reason=(f"Rung {rung} policy forbids {category.value} actions. "
                    f"Promote the agent to allow this action."),
            policy_rules_applied=rules_applied,
            context=context,
        )

    if category in policy.allowed_actions:
        amount = context.get("amount") or context.get("value")
        if (category == ActionCategory.FINANCIAL
                and policy.max_financial_amount is not None
                and isinstance(amount, (int, float))
                and float(amount) > policy.max_financial_amount):
            rules_applied.append(
                f"rung{rung}.financial_cap: ${amount} exceeds limit "
                f"${policy.max_financial_amount}"
            )
            return PolicyEvaluation(
                agent_id=agent_id, assignment_id=assignment_id, rung=rung,
                action=action, action_category=category,
                outcome=PolicyOutcome.ESCALATE,
                reason=(
                    f"Financial amount ${amount:,.2f} exceeds rung {rung} limit "
                    f"of ${policy.max_financial_amount:,.2f}. Human co-sign required."
                ),
                policy_rules_applied=rules_applied, context=context,
            )

        if not _check_rate_limit(agent_id, category, policy):
            limit = policy.rate_limits.get(category.value, 0)
            rules_applied.append(f"rung{rung}.rate_limit: {category.value} > {limit}/min")
            return PolicyEvaluation(
                agent_id=agent_id, assignment_id=assignment_id, rung=rung,
                action=action, action_category=category,
                outcome=PolicyOutcome.RATE_LIMIT,
                reason=(f"Rate limit exceeded: rung {rung} allows at most "
                        f"{limit} {category.value} operations per minute."),
                policy_rules_applied=rules_applied, context=context,
            )

        rules_applied.append(f"rung{rung}.allow: {category.value}")
        return PolicyEvaluation(
            agent_id=agent_id, assignment_id=assignment_id, rung=rung,
            action=action, action_category=category,
            outcome=PolicyOutcome.ALLOW,
            reason=f"Rung {rung} permits {category.value} actions.",
            policy_rules_applied=rules_applied, context=context,
        )

    if category in policy.require_approval_actions:
        rules_applied.append(
            f"rung{rung}.require_approval: {category.value} needs co-sign"
        )
        return PolicyEvaluation(
            agent_id=agent_id, assignment_id=assignment_id, rung=rung,
            action=action, action_category=category,
            outcome=PolicyOutcome.REQUIRE_APPROVAL,
            reason=(f"Rung {rung} requires human co-sign for {category.value} actions. "
                    f"Submit a co-sign request before executing."),
            policy_rules_applied=rules_applied, context=context,
        )

    rules_applied.append(f"rung{rung}.default_deny: {category.value} not in allowlist")
    return PolicyEvaluation(
        agent_id=agent_id, assignment_id=assignment_id, rung=rung,
        action=action, action_category=category,
        outcome=PolicyOutcome.DENY,
        reason=f"Action category '{category.value}' not in rung {rung} allowlist.",
        policy_rules_applied=rules_applied, context=context,
    )


def reset_rate_counters(agent_id: str | None = None) -> None:
    if agent_id:
        _rate_counters.pop(agent_id, None)
    else:
        _rate_counters.clear()
