"""Decision Atlas — the discovery engine for agentic transformation.

Decision Atlas crawls existing workflow systems, ticketing platforms, approval
chains, and audit logs to auto-build a live map of every decision across the
enterprise: who owns it, what data feeds it, what "correct" looks like, and a
recommended target autonomy rung. It is the first service of the AgenticLadder
platform — the map you point your agents at.
"""
from __future__ import annotations

from .connectors import available_connectors, build_connector
from .discovery import DiscoveryEngine
from .graph import build_graph, export
from .models import Decision, DecisionEvent, Domain
from .rung import LADDER, recommend, rung_name

__version__ = "0.1.0"

__all__ = [
    "DiscoveryEngine",
    "build_graph",
    "export",
    "recommend",
    "rung_name",
    "LADDER",
    "Decision",
    "DecisionEvent",
    "Domain",
    "available_connectors",
    "build_connector",
    "__version__",
]
