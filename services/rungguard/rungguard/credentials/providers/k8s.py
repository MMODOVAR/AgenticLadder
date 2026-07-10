"""Kubernetes ServiceAccount token credential provider."""
from __future__ import annotations

import base64
import json
import secrets
from typing import Any

from ...models import RungCredential, RungPolicy
from .base import CredentialProvider, register_provider

RUNG_SA_MAP = {
    0: "rungguard-manual-sa",
    1: "rungguard-assisted-sa",
    2: "rungguard-recommended-sa",
    3: "rungguard-supervised-sa",
    4: "rungguard-conditional-sa",
    5: "rungguard-autonomous-sa",
}


@register_provider("k8s")
class KubernetesCredentialProvider(CredentialProvider):
    def __init__(
        self,
        namespace: str = "rungguard",
        cluster_name: str = "prod",
        k8s_sdk: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.namespace = namespace
        self.cluster_name = cluster_name
        self.k8s_sdk = k8s_sdk

    def issue(self, agent_id: str, rung: int, policy: RungPolicy,
              ttl_seconds: int | None = None) -> RungCredential:
        ttl = ttl_seconds or policy.credential_ttl_seconds or 3600
        sa_name = RUNG_SA_MAP.get(rung, f"rungguard-rung{rung}-sa")

        if self.k8s_sdk:
            from kubernetes import client as k8s_client, config as k8s_config  # type: ignore[import]
            k8s_config.load_incluster_config()
            v1 = k8s_client.CoreV1Api()
            token_request = k8s_client.AuthenticationV1TokenRequest(
                spec=k8s_client.AuthenticationV1TokenRequestSpec(
                    expiration_seconds=ttl,
                    audiences=["https://kubernetes.default.svc"],
                )
            )
            resp = v1.create_namespaced_service_account_token(
                name=sa_name,
                namespace=self.namespace,
                body=token_request,
            )
            secret_ref = resp.status.token
        else:
            header = base64.urlsafe_b64encode(
                json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
            ).decode().rstrip("=")
            payload = base64.urlsafe_b64encode(
                json.dumps({
                    "iss": f"https://{self.cluster_name}.k8s.example.com",
                    "sub": f"system:serviceaccount:{self.namespace}:{sa_name}",
                    "aud": ["https://kubernetes.default.svc"],
                }).encode()
            ).decode().rstrip("=")
            sig = secrets.token_urlsafe(43)
            secret_ref = f"{header}.{payload}.{sig}"

        return self._make_credential(
            agent_id=agent_id,
            assignment_id="",
            rung=rung,
            credential_type="k8s_service_account_token",
            secret_ref=secret_ref,
            ttl_seconds=ttl,
            metadata={
                "namespace": self.namespace,
                "service_account": sa_name,
                "cluster": self.cluster_name,
                "stub": not self.k8s_sdk,
            },
        )

    def revoke(self, credential_id: str, secret_ref: str,
               metadata: dict[str, Any]) -> None:
        if not self.k8s_sdk:
            return
        try:
            from kubernetes import client as k8s_client, config as k8s_config  # type: ignore[import]
            k8s_config.load_incluster_config()
            v1 = k8s_client.CoreV1Api()
            v1.delete_namespaced_secret(
                name=f"rungguard-token-{credential_id}",
                namespace=self.namespace,
            )
        except Exception:
            pass
