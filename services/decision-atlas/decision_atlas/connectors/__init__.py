"""Connector registry. Importing this package registers all built-in connectors."""
from .base import (
    Connector,
    available_connectors,
    build_connector,
    register_connector,
)

# Import side effects register each connector in the registry.
from . import audit_log  # noqa: F401
from . import jira  # noqa: F401
from . import approval  # noqa: F401
from . import workflow  # noqa: F401

__all__ = [
    "Connector",
    "available_connectors",
    "build_connector",
    "register_connector",
]
