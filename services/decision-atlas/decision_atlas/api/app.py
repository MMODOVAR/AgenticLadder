"""FastAPI surface for Decision Atlas.

Exposes discovery, the decision map, owner annotation/approval, and graph export,
plus serves the annotation dashboard. FastAPI is an optional dependency — the
core engine works without it; importing this module raises a clear message if
FastAPI is not installed.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import HTMLResponse, PlainTextResponse
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "FastAPI is required for the API. Install with: pip install 'fastapi' 'uvicorn'"
    ) from exc

from ..discovery import DiscoveryEngine
from ..graph import build_graph, export
from ..rung.ladder import LADDER
from .store import AtlasStore

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
SAMPLE_CONFIG = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "sample_data", "config.json"
)

store = AtlasStore()
app = FastAPI(
    title="Decision Atlas",
    version="0.1.0",
    description="Auto-built, live map of enterprise decisions for agentic transformation.",
)


# --- request models ---------------------------------------------------------


class DiscoverRequest(BaseModel):
    config: Optional[dict[str, Any]] = None
    config_path: Optional[str] = None


class AnnotateRequest(BaseModel):
    owner: Optional[str] = None
    owner_role: Optional[str] = None
    criteria: Optional[str] = None
    notes: Optional[str] = None
    signal_overrides: Optional[dict[str, float]] = None
    target_rung_override: Optional[int] = None


class ApproveRequest(BaseModel):
    approved_by: str


# --- routes -----------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    path = os.path.join(WEB_DIR, "dashboard.html")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@app.get("/api/ladder")
def get_ladder() -> dict[str, Any]:
    return {"rungs": [
        {"level": r.level, "name": r.name, "summary": r.summary,
         "human_role": r.human_role}
        for r in LADDER
    ]}


@app.post("/api/discover")
def discover(req: DiscoverRequest) -> dict[str, Any]:
    config = req.config
    base_dir = None
    if config is None:
        path = req.config_path or SAMPLE_CONFIG
        if not os.path.exists(path):
            raise HTTPException(404, f"Config not found: {path}")
        with open(path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
        base_dir = os.path.dirname(os.path.abspath(path))
    try:
        engine = DiscoveryEngine.from_config(config, base_dir=base_dir)
        domains = engine.discover()
    except Exception as exc:  # surface connector/config errors cleanly
        raise HTTPException(400, f"Discovery failed: {exc}") from exc
    store.load_domains(domains)
    return store.summary()


@app.get("/api/summary")
def summary() -> dict[str, Any]:
    return store.summary()


@app.get("/api/domains")
def list_domains() -> dict[str, Any]:
    return {"domains": [
        {"name": d.name, "decision_count": len(d.decisions)}
        for d in store.domains()
    ]}


@app.get("/api/domains/{domain}/decisions")
def domain_decisions(domain: str) -> dict[str, Any]:
    dom = store.get_domain(domain)
    if dom is None:
        raise HTTPException(404, f"Domain not found: {domain}")
    return dom.to_dict()


@app.get("/api/decisions/{decision_id}")
def get_decision(decision_id: str) -> dict[str, Any]:
    dec = store.get_decision(decision_id)
    if dec is None:
        raise HTTPException(404, "Decision not found")
    return dec.to_dict()


@app.post("/api/decisions/{decision_id}/annotate")
def annotate(decision_id: str, req: AnnotateRequest) -> dict[str, Any]:
    if store.get_decision(decision_id) is None:
        raise HTTPException(404, "Decision not found")
    dec = store.annotate(decision_id, req.model_dump(exclude_unset=True))
    return dec.to_dict()


@app.post("/api/decisions/{decision_id}/approve")
def approve(decision_id: str, req: ApproveRequest) -> dict[str, Any]:
    if store.get_decision(decision_id) is None:
        raise HTTPException(404, "Decision not found")
    dec = store.approve(decision_id, req.approved_by)
    return dec.to_dict()


@app.get("/api/domains/{domain}/graph")
def domain_graph(domain: str, format: str = "json"):
    dom = store.get_domain(domain)
    if dom is None:
        raise HTTPException(404, f"Domain not found: {domain}")
    graph = build_graph(dom)
    if format == "json":
        return graph.to_dict()
    try:
        body = export(graph, format)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return PlainTextResponse(body)
