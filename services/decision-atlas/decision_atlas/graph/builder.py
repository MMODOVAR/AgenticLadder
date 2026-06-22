"""Build a decision graph for a domain.

Nodes: decisions, the data inputs that feed them, and the owners/roles that own
them. Edges:

* owner  --owns-->     decision
* input  --feeds-->    decision
* decision --depends--> decision   (inferred when one decision's name/key appears
                                    as another's input field — i.e. an output of
                                    A is consumed by B)

The graph is the exportable artifact a domain owner walks away with: a live
"decision graph" they can point an agentic transformation at.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import Decision, Domain


@dataclass
class Node:
    id: str
    label: str
    type: str  # "decision" | "input" | "owner"
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str
    type: str  # "owns" | "feeds" | "depends"


@dataclass
class DecisionGraph:
    domain: str
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "nodes": [
                {"id": n.id, "label": n.label, "type": n.type, **n.attrs}
                for n in self.nodes
            ],
            "edges": [
                {"source": e.source, "target": e.target, "type": e.type}
                for e in self.edges
            ],
        }


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def build_graph(domain: Domain) -> DecisionGraph:
    graph = DecisionGraph(domain=domain.name)
    seen_nodes: set[str] = set()

    def add_node(node: Node) -> None:
        if node.id not in seen_nodes:
            graph.nodes.append(node)
            seen_nodes.add(node.id)

    # Index decisions by normalized key/name token for dependency inference.
    decision_tokens: dict[str, str] = {}
    for d in domain.decisions:
        for token in {_norm(d.name), _norm(d.key.split(".")[-1])}:
            if token:
                decision_tokens[token] = d.id

    for d in domain.decisions:
        rec = d.recommendation
        add_node(Node(
            id=d.id,
            label=d.name,
            type="decision",
            attrs={
                "key": d.key,
                "event_count": d.event_count,
                "recommended_rung": rec.recommended_rung if rec else None,
                "rung_name": rec.rung_name if rec else None,
                "status": d.status.value,
            },
        ))

        owner = d.annotation.owner or d.owner or d.annotation.owner_role or d.owner_role
        if owner:
            oid = f"owner:{_norm(owner)}"
            add_node(Node(id=oid, label=owner, type="owner"))
            graph.edges.append(Edge(oid, d.id, "owns"))

        for inp in d.input_data:
            iid = f"input:{_norm(inp)}"
            add_node(Node(id=iid, label=inp, type="input"))
            graph.edges.append(Edge(iid, d.id, "feeds"))

            # Dependency inference: does this input correspond to another
            # decision's output?
            token = _norm(inp)
            dep = decision_tokens.get(token)
            if dep and dep != d.id:
                graph.edges.append(Edge(dep, d.id, "depends"))

    # De-duplicate edges.
    unique: list[Edge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for e in graph.edges:
        sig = (e.source, e.target, e.type)
        if sig not in seen_edges:
            seen_edges.add(sig)
            unique.append(e)
    graph.edges = unique
    return graph
