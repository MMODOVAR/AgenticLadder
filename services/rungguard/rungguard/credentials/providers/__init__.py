"""Credential provider registry. Importing registers all built-in providers."""
from .base import (
    CredentialProvider,
    available_providers,
    build_provider,
    register_provider,
)

# Side-effect imports register each provider.
from . import env     # noqa: F401
from . import aws     # noqa: F401
from . import azure   # noqa: F401
from . import gcp     # noqa: F401
from . import vault   # noqa: F401
from . import k8s     # noqa: F401

__all__ = [
    "CredentialProvider",
    "available_providers",
    "build_provider",
    "register_provider",
]
