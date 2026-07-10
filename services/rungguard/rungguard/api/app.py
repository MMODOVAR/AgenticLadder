"""RungGuard REST API — the control plane surface.

Exposes the full rung lifecycle: agent registration, promotion/demotion
workflows, approval actions, policy checks, credential status, and the
rung-tagged audit log. Also serves the control plane dashboard.
"""
from __future__ import annotations

import os
from typing import Any, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, PlainTextResponse
    from pydantic import BaseModel
except ImportError as exc:
    raise ImportError(
        "FastAPI is required. Install with: pip install fastapi uvicorn"
    ) from exc

from .store import ControlPlane
from ..models import ChangeDirection
from ..policies.rules import all_policies

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")

plane = ControlPlane()
app = FastAPI(
    title="RungGuard",
    version="0.1.0",
    description=(
        "Control plane that treats the autonomy rung as a governable object: "
        "promotion/demotion workflows, automatic credential rotation, "
        "blast-radius policies, and rung-tagged audit log."
    ),
)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class RegisterAgentRequest(BaseModel):
    name: str
    owner: str
    owner_email: str = ""
    description: str = ""
    tags: dict[str, str] = {}
    initial_rung: int = 0

class SubmitChangeRequest(BaseModel):
    to_rung: int
    requested_by: str
    justification: str
    direction: Optional[str] = None

class ApprovalRequest(BaseModel):
    approver: str
    approver_role: str
    notes: str = ""

class CancelRequest(BaseModel):
    cancelled_by: str

class CheckActionRequest(BaseModel):
    action: str
    context: dict[str, Any] = {}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    path = os.path.join(WEB_DIR, "dashboard.html")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()

@app.get("/api/summary")
def summary() -> dict[str, Any]:
    return plane.summary()

@app.get("/api/policies")
def list_policies() -> dict[str, Any]:
    return {"policies": plane.policies()}

# --- agents -----------------------------------------------------------------

@app.post("/api/agents", status_code=201)
def register_agent(req: RegisterAgentRequest) -> dict[str, Any]:
    agent = plane.register_agent(
        name=req.name, owner=req.owner, owner_email=req.owner_email,
        description=req.description, tags=req.tags, initial_rung=req.initial_rung,
    )
    return agent.to_dict()

@app.get("/api/agents")
def list_agents() -> dict[str, Any]:
    return {"agents": [a.to_dict() for a in plane.list_agents()]}

@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: str) -> dict[str, Any]:
    agent = plane.get_agent(agent_id)
    if agent is None:
        raise HTTPException(404, f"Agent not found: {agent_id}")
    return agent.to_dict()

@app.get("/api/agents/{agent_id}/credentials")
def agent_credentials(agent_id: str) -> dict[str, Any]:
    if plane.get_agent(agent_id) is None:
        raise HTTPException(404, "Agent not found")
    return {
        "active": [c.to_dict() for c in plane.cred_manager.active_for_agent(agent_id)],
        "all": [c.to_dict() for c in plane.cred_manager.all_for_agent(agent_id)],
    }

@app.get("/api/agents/{agent_id}/history")
def agent_history(agent_id: str) -> dict[str, Any]:
    if plane.get_agent(agent_id) is None:
        raise HTTPException(404, "Agent not found")
    return {
        "assignments": [
            a.to_dict()
            for a in plane.lifecycle.get_agent_history(agent_id)
        ],
        "audit": [
            e.to_dict()
            for e in plane.audit.for_agent(agent_id)
        ],
    }

@app.post("/api/agents/{agent_id}/check")
def check_action(agent_id: str, req: CheckActionRequest) -> dict[str, Any]:
    if plane.get_agent(agent_id) is None:
        raise HTTPException(404, "Agent not found")
    try:
        result = plane.check_action(agent_id, req.action, req.context)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return result.to_dict()

# --- change requests --------------------------------------------------------

@app.post("/api/agents/{agent_id}/change-requests", status_code=201)
def submit_change_request(agent_id: str, req: SubmitChangeRequest) -> dict[str, Any]:
    if plane.get_agent(agent_id) is None:
        raise HTTPException(404, "Agent not found")
    direction = None
    if req.direction:
        try:
            direction = ChangeDirection(req.direction)
        except ValueError:
            raise HTTPException(400, f"Invalid direction: {req.direction}")
    try:
        change_req = plane.submit_change_request(
            agent_id=agent_id,
            to_rung=req.to_rung,
            requested_by=req.requested_by,
            justification=req.justification,
            direction=direction,
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return change_req.to_dict()

@app.get("/api/change-requests")
def list_change_requests(status: Optional[str] = None) -> dict[str, Any]:
    return {"requests": [r.to_dict() for r in plane.list_requests(status)]}

@app.get("/api/change-requests/{request_id}")
def get_change_request(request_id: str) -> dict[str, Any]:
    req = plane._requests.get(request_id)
    if req is None:
        raise HTTPException(404, "Request not found")
    return req.to_dict()

@app.post("/api/change-requests/{request_id}/approve")
def approve_step(request_id: str, req: ApprovalRequest) -> dict[str, Any]:
    if request_id not in plane._requests:
        raise HTTPException(404, "Request not found")
    try:
        updated = plane.approve_step(request_id, req.approver, req.approver_role, req.notes)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return updated.to_dict()

@app.post("/api/change-requests/{request_id}/reject")
def reject_step(request_id: str, req: ApprovalRequest) -> dict[str, Any]:
    if request_id not in plane._requests:
        raise HTTPException(404, "Request not found")
    try:
        updated = plane.reject_step(request_id, req.approver, req.approver_role, req.notes)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return updated.to_dict()

@app.post("/api/change-requests/{request_id}/cancel")
def cancel_request(request_id: str, req: CancelRequest) -> dict[str, Any]:
    if request_id not in plane._requests:
        raise HTTPException(404, "Request not found")
    try:
        updated = plane.cancel_request(request_id, req.cancelled_by)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return updated.to_dict()

# --- audit log --------------------------------------------------------------

@app.get("/api/audit")
def get_audit(limit: int = 100) -> dict[str, Any]:
    return {
        "entries": [e.to_dict() for e in plane.audit.recent(limit)],
        "stats": plane.audit.stats(),
    }

@app.get("/api/audit/export")
def export_audit() -> PlainTextResponse:
    return PlainTextResponse(plane.audit.export_jsonl(),
                             media_type="application/x-ndjson")
