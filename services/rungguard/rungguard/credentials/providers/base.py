"""Abstract credential provider and plugin registry."""
from __future__ import annotations

import abc
from typing import Any, Callable

from ...models import RungCredential, RungPolicy, _uid, _ts
from datetime import datetime, timezone, timedelta

_REGISTRY: dict[str, type["CredentialProvider"]] = {}


def register_provider(type_name: str) -> Callable:
    def deco(cls: type["CredentialProvider"]) -> type["CredentialProvider"]:
        cls.type_name = type_name
        _REGISTRY[type_name] = cls
        return cls
    return deco


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def build_provider(spec: dict[str, Any]) -> "CredentialProvider":
    type_name = spec.get("type")
    if type_name not in _REGISTRY:
        raise ValueError(
            f"Unknown credential provider {type_name!r}. "
            f"Available: {', '.join(available_providers()) or '(none)'}"
        )
    options = {k: v for k, v in spec.items() if k != "type"}
    return _REGISTRY[type_name](**options)


class CredentialProvider(abc.ABC):
    type_name: str = "base"

    def __init__(self, name: str | None = None, **kwargs: Any) -> None:
        self.name = name or self.type_name
        self.options = kwargs

    @abc.abstractmethod
    def issue(self, agent_id: str, rung: int, policy: RungPolicy,
              ttl_seconds: int | None = None) -> RungCredential:
        raise NotImplementedError

    @abc.abstractmethod
    def revoke(self, credential_id: str, secret_ref: str,
               metadata: dict[str, Any]) -> None:
        raise NotImplementedError

    def rotate(self, old_credential: RungCredential, agent_id: str,
               rung: int, policy: RungPolicy) -> RungCredential:
        new = self.issue(agent_id, rung, policy,
                         ttl_seconds=policy.credential_ttl_seconds)
        self.revoke(old_credential.id, old_credential.secret_ref,
                    old_credential.provider_metadata)
        return new

    def _make_credential(self, agent_id: str, assignment_id: str, rung: int,
                         credential_type: str, secret_ref: str,
                         ttl_seconds: int | None,
                         metadata: dict[str, Any] | None = None) -> RungCredential:
        now = datetime.now(timezone.utc)
        expires_at = (
            (now + timedelta(seconds=ttl_seconds)).isoformat()
            if ttl_seconds else None
        )
        return RungCredential(
            id=_uid("cred_"),
            agent_id=agent_id,
            assignment_id=assignment_id,
            rung=rung,
            provider=self.type_name,
            credential_type=credential_type,
            secret_ref=secret_ref,
            issued_at=_ts(now),
            expires_at=expires_at,
            provider_metadata=metadata or {},
        )

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
