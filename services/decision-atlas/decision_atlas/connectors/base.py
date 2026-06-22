"""Connector framework.

A *connector* adapts one source system — a ticketing platform, an approval/ITSM
tool, a workflow/BPM engine, a raw audit log on any cloud — into a stream of
canonical :class:`DecisionEvent` objects. Because everything downstream operates
on the canonical model, Decision Atlas is agnostic to the cloud, language, or
application a source is built on. Adding support for a new system is just
writing a new connector and registering it.

To add a connector:

    from .base import Connector, register_connector

    @register_connector("my_system")
    class MyConnector(Connector):
        def fetch_events(self) -> list[DecisionEvent]:
            ...

Then reference it from a discovery config by ``"type": "my_system"``.
"""
from __future__ import annotations

import abc
from typing import Any, Callable

from ..models import DecisionEvent

# Connector type name -> class
_REGISTRY: dict[str, type["Connector"]] = {}


def register_connector(type_name: str) -> Callable[[type["Connector"]], type["Connector"]]:
    def deco(cls: type["Connector"]) -> type["Connector"]:
        cls.type_name = type_name
        _REGISTRY[type_name] = cls
        return cls
    return deco


def available_connectors() -> list[str]:
    return sorted(_REGISTRY)


def build_connector(spec: dict[str, Any]) -> "Connector":
    """Instantiate a connector from a config spec.

    ``spec`` must contain ``type`` and may contain ``name`` plus any
    connector-specific options.
    """
    type_name = spec.get("type")
    if type_name not in _REGISTRY:
        raise ValueError(
            f"Unknown connector type {type_name!r}. "
            f"Available: {', '.join(available_connectors()) or '(none)'}"
        )
    options = {k: v for k, v in spec.items() if k not in ("type",)}
    return _REGISTRY[type_name](**options)


class Connector(abc.ABC):
    """Base class for all source connectors."""

    type_name: str = "base"

    def __init__(self, name: str | None = None, domain: str | None = None,
                 **kwargs: Any) -> None:
        self.name = name or self.type_name
        self.default_domain = domain
        self.options = kwargs

    @abc.abstractmethod
    def fetch_events(self) -> list[DecisionEvent]:
        """Pull raw records from the source and normalize to DecisionEvents."""
        raise NotImplementedError

    # Convenience for subclasses ------------------------------------------------

    def _new_event(self, **kwargs: Any) -> DecisionEvent:
        kwargs.setdefault("source", self.name)
        kwargs.setdefault("source_type", self.type_name)
        if kwargs.get("domain") is None and self.default_domain:
            kwargs["domain"] = self.default_domain
        return DecisionEvent(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} name={self.name!r}>"
