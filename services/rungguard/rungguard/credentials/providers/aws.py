"""AWS credential provider (STS assume-role + Secrets Manager)."""
from __future__ import annotations

import json
import secrets
from typing import Any

from ...models import RungCredential, RungPolicy
from .base import CredentialProvider, register_provider

RUNG_ROLE_SUFFIX = {
    0: "manual",
    1: "assisted-readonly",
    2: "recommended-draft",
    3: "supervised-write",
    4: "conditional-execute",
    5: "autonomous-full",
}


@register_provider("aws")
class AWSCredentialProvider(CredentialProvider):
    def __init__(
        self,
        account_id: str = "123456789012",
        role_prefix: str = "rungguard",
        region: str = "us-east-1",
        strategy: str = "sts_assume_role",
        aws_sdk: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.account_id = account_id
        self.role_prefix = role_prefix
        self.region = region
        self.strategy = strategy
        self.aws_sdk = aws_sdk

    def _role_arn(self, rung: int) -> str:
        suffix = RUNG_ROLE_SUFFIX.get(rung, f"rung{rung}")
        return f"arn:aws:iam::{self.account_id}:role/{self.role_prefix}-{suffix}"

    def issue(self, agent_id: str, rung: int, policy: RungPolicy,
              ttl_seconds: int | None = None) -> RungCredential:
        ttl = ttl_seconds or policy.credential_ttl_seconds or 3600
        role_arn = self._role_arn(rung)

        if self.aws_sdk:
            import boto3  # type: ignore[import]
            client = boto3.client("sts", region_name=self.region)
            resp = client.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f"rungguard-{agent_id}-rung{rung}",
                DurationSeconds=min(ttl, 43200),
            )
            creds = resp["Credentials"]
            secret_ref = json.dumps({
                "AccessKeyId": creds["AccessKeyId"],
                "SecretAccessKey": creds["SecretAccessKey"],
                "SessionToken": creds["SessionToken"],
            })
        else:
            secret_ref = json.dumps({
                "AccessKeyId": f"ASIA{secrets.token_hex(8).upper()}",
                "SecretAccessKey": secrets.token_urlsafe(40),
                "SessionToken": secrets.token_urlsafe(80),
            })

        return self._make_credential(
            agent_id=agent_id,
            assignment_id="",
            rung=rung,
            credential_type="aws_sts_role",
            secret_ref=secret_ref,
            ttl_seconds=ttl,
            metadata={
                "role_arn": role_arn,
                "region": self.region,
                "strategy": self.strategy,
                "stub": not self.aws_sdk,
            },
        )

    def revoke(self, credential_id: str, secret_ref: str,
               metadata: dict[str, Any]) -> None:
        if not self.aws_sdk:
            return
        try:
            import boto3  # type: ignore[import]
            iam = boto3.client("iam", region_name=self.region)
            role_arn = metadata.get("role_arn", "")
            role_name = role_arn.split("/")[-1]
            iam.tag_role(
                RoleName=role_name,
                Tags=[{"Key": f"revoked-session-{credential_id}", "Value": "true"}],
            )
        except Exception:
            pass
