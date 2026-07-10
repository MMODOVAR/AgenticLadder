"""GCP Secret Manager credential provider."""
from __future__ import annotations

import json
import secrets
from typing import Any

from ...models import RungCredential, RungPolicy
from .base import CredentialProvider, register_provider

RUNG_SA_MAP = {
    0: "rungguard-manual",
    1: "rungguard-assisted",
    2: "rungguard-recommended",
    3: "rungguard-supervised",
    4: "rungguard-conditional",
    5: "rungguard-autonomous",
}


@register_provider("gcp")
class GCPCredentialProvider(CredentialProvider):
    def __init__(
        self,
        project_id: str = "my-project",
        location: str = "global",
        gcp_sdk: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.project_id = project_id
        self.location = location
        self.gcp_sdk = gcp_sdk

    def _secret_id(self, agent_id: str, rung: int) -> str:
        return f"rungguard-{agent_id[:8]}-rung{rung}"

    def issue(self, agent_id: str, rung: int, policy: RungPolicy,
              ttl_seconds: int | None = None) -> RungCredential:
        ttl = ttl_seconds or policy.credential_ttl_seconds
        secret_id = self._secret_id(agent_id, rung)

        if self.gcp_sdk:
            from google.cloud import secretmanager  # type: ignore[import]
            client = secretmanager.SecretManagerServiceClient()
            parent = f"projects/{self.project_id}"
            try:
                client.create_secret(
                    request={"parent": parent,
                             "secret_id": secret_id,
                             "secret": {"replication": {"automatic": {}}}}
                )
            except Exception:
                pass
            token = secrets.token_urlsafe(32)
            version = client.add_secret_version(
                request={"parent": f"{parent}/secrets/{secret_id}",
                         "payload": {"data": token.encode()}}
            )
            secret_ref = version.name
            version_id = secret_ref.split("/")[-1]
        else:
            token = secrets.token_urlsafe(32)
            version_id = str(secrets.randbelow(9000) + 1000)
            secret_ref = (
                f"projects/{self.project_id}/secrets/{secret_id}"
                f"/versions/{version_id}"
            )

        return self._make_credential(
            agent_id=agent_id,
            assignment_id="",
            rung=rung,
            credential_type="gcp_secret_version",
            secret_ref=secret_ref,
            ttl_seconds=ttl,
            metadata={
                "project_id": self.project_id,
                "secret_id": secret_id,
                "version": version_id,
                "service_account": (
                    f"{RUNG_SA_MAP.get(rung, f'rungguard-rung{rung}')}"
                    f"@{self.project_id}.iam.gserviceaccount.com"
                ),
                "stub": not self.gcp_sdk,
            },
        )

    def revoke(self, credential_id: str, secret_ref: str,
               metadata: dict[str, Any]) -> None:
        if not self.gcp_sdk:
            return
        try:
            from google.cloud import secretmanager  # type: ignore[import]
            client = secretmanager.SecretManagerServiceClient()
            client.destroy_secret_version(request={"name": secret_ref})
        except Exception:
            pass
