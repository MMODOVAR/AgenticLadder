"""RungGuard — autonomy-rung governance control plane.

Public API surface:
    ControlPlane  — wires lifecycle, credentials, policies, and audit
    AuditLog      — rung-tagged append-only event log
    register_writer — plug in an external log sink (CloudWatch, Splunk …)
"""
from .api.store import ControlPlane
from .audit.log import AuditLog, register_writer

__version__ = "0.1.0"
__all__ = ["ControlPlane", "AuditLog", "register_writer"]
