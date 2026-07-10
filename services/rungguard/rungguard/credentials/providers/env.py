"""Environment / generic token provider."""
from __future__ import annotations

import os
import secrets
from typing import Any

from ...models import RungCredential, RungPolicy, CredentialStatus, _ts
from .base import CredentialProvider, register_provider

_TOKEN_STORE: dict[str, str] = {}


@register_provider("env")
class EnvCredentialProvider(CredentialProvider):
    def __init__(self, prefix: str = "RUNGGUARD_TOKEN", write_env: bool = False,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.prefix = prefix
        self.write_env = write_env

    def issue(self, agent_id: str, rung: int, policy: RungPolicy,
              ttl_seconds: int | None = None) -> RungCredential:
        token = secrets.token_urlsafe(32)
        env_key = f"{self.prefix}_{agent_id.upper()}_RUNG{rung}"
        secret_ref = env_key
        _TOKEN_STORE[env_key] = token
        if self.write_env:
            os.environ[env_key] = token

        return self._make_credential(
            agent_id=agent_id,
            assignment_id="",
            rung=rung,
            credential_type="api_token",
            secret_ref=secret_ref,
            ttl_seconds=ttl_seconds or policy.credential_ttl_seconds,
            metadata={"env_key": env_key, "write_env": self.write_env},
        )

    def revoke(self, credential_id: str, secret_ref: str,
               metadata: dict[str, Any]) -> None:
        env_key = metadata.get("env_key", secret_ref)
        _TOKEN_STORE.pop(env_key, None)
        if self.write_env and env_key in os.environ:
            os.environ.pop(env_key, None)

    def lookup(self, secret_ref: str) -> str | None:
        return _TOKEN_STORE.get(secret_ref)
