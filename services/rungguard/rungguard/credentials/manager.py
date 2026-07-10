"""Credential rotation manager."""
from __future__ import annotations

from typing import Any

from ..models import (
    Agent,
    CredentialStatus,
    RungAssignment,
    RungCredential,
    _now,
    _ts,
)
from ..policies.rules import get_policy
from .providers import CredentialProvider, available_providers, build_provider
from .providers.env import EnvCredentialProvider


class CredentialManager:
    def __init__(
        self,
        credentials: dict[str, RungCredential],
        provider: CredentialProvider | None = None,
    ) -> None:
        self._credentials = credentials
        self._provider = provider or EnvCredentialProvider(name="default-env")

    @classmethod
    def from_spec(cls, spec: dict[str, Any],
                  credentials: dict[str, RungCredential]) -> "CredentialManager":
        provider = build_provider(spec)
        return cls(credentials, provider)

    def on_rung_change(self, agent: Agent, new_assignment: RungAssignment) -> None:
        self._revoke_all(agent.id, reason=f"Rung changed to {new_assignment.rung}")
        if new_assignment.rung > 0 and agent.status.value == "active":
            self._issue(agent.id, new_assignment)

    def issue_initial(self, agent: Agent, assignment: RungAssignment) -> RungCredential | None:
        if assignment.rung == 0:
            return None
        return self._issue(agent.id, assignment)

    def _issue(self, agent_id: str, assignment: RungAssignment) -> RungCredential:
        policy = get_policy(assignment.rung)
        cred = self._provider.issue(
            agent_id=agent_id,
            rung=assignment.rung,
            policy=policy,
            ttl_seconds=policy.credential_ttl_seconds,
        )
        cred.assignment_id = assignment.id
        self._credentials[cred.id] = cred
        return cred

    def _revoke_all(self, agent_id: str, reason: str = "") -> list[str]:
        revoked_ids = []
        for cred in self._credentials.values():
            if cred.agent_id == agent_id and cred.status == CredentialStatus.ACTIVE:
                try:
                    self._provider.revoke(cred.id, cred.secret_ref,
                                          cred.provider_metadata)
                except Exception:
                    pass
                cred.status = CredentialStatus.REVOKED
                cred.revoked_at = _ts()
                cred.revocation_reason = reason
                revoked_ids.append(cred.id)
        return revoked_ids

    def expire_stale(self) -> list[str]:
        expired = []
        now = _now().isoformat()
        for cred in self._credentials.values():
            if (cred.status == CredentialStatus.ACTIVE
                    and cred.expires_at is not None
                    and now >= cred.expires_at):
                cred.status = CredentialStatus.EXPIRED
                expired.append(cred.id)
        return expired

    def active_for_agent(self, agent_id: str) -> list[RungCredential]:
        return [c for c in self._credentials.values()
                if c.agent_id == agent_id
                and c.status == CredentialStatus.ACTIVE
                and not c.is_expired()]

    def all_for_agent(self, agent_id: str) -> list[RungCredential]:
        return sorted(
            [c for c in self._credentials.values() if c.agent_id == agent_id],
            key=lambda c: c.issued_at, reverse=True,
        )

    def summary(self) -> dict[str, Any]:
        creds = list(self._credentials.values())
        return {
            "total": len(creds),
            "active": sum(1 for c in creds if c.status == CredentialStatus.ACTIVE),
            "revoked": sum(1 for c in creds if c.status == CredentialStatus.REVOKED),
            "expired": sum(1 for c in creds if c.status == CredentialStatus.EXPIRED),
            "provider": self._provider.type_name,
        }
