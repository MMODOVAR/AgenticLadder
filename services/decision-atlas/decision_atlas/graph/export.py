"""Export a DecisionGraph to interchange formats.

* ``json``    — node-link JSON (works with D3, cytoscape, anything)
* ``dot``     — Graphviz DOT
* ``mermaid`` — Mermaid flowchart (renders in Markdown/GitHub/docs)
* ``graphml`` — GraphML (yEd, Gephi, Cytoscape, enterprise EA tools)
"""
from __future__ import annotations

import json
from xml.sax.saxutils import escape

from .builder import DecisionGraph

_EDGE_STYLE = {
    "owns": ("owns", "dashed"),
    "feeds": ("feeds", "solid"),
    "depends": ("depends on", "bold"),
}

_NODE_COLOR = {
    "decision": "#2563eb",
    "input": "#64748b",
    "owner": "#16a34a",
}


def to_json(graph: DecisionGraph, indent: int = 2) -> str:
    return json.dumps(graph.to_dict(), indent=indent)


def to_dot(graph: DecisionGraph) -> str:
    lines = [f'digraph "{graph.domain}" {{', "  rankdir=LR;",
             '  node [style=filled, fontname="Helvetica"];']
    for n in graph.nodes:
        color = _NODE_COLOR.get(n.type, "#cccccc")
        shape = "box" if n.type == "decision" else (
            "ellipse" if n.type == "owner" else "note")
        label = n.label
        if n.type == "decision" and n.attrs.get("rung_name") is not None:
            label = f"{n.label}\\nRung {n.attrs['recommended_rung']}: {n.attrs['rung_name']}"
        lines.append(
            f'  "{n.id}" [label="{_dot_escape(label)}", shape={shape}, '
            f'fillcolor="{color}", fontcolor=white];'
        )
    for e in graph.edges:
        label, style = _EDGE_STYLE.get(e.type, (e.type, "solid"))
        lines.append(
            f'  "{e.source}" -> "{e.target}" [label="{label}", style={style}];'
        )
    lines.append("}")
    return "\n".join(lines)


def to_mermaid(graph: DecisionGraph) -> str:
    lines = ["flowchart LR"]
    safe = {n.id: f"n{i}" for i, n in enumerate(graph.nodes)}
    for n in graph.nodes:
        nid = safe[n.id]
        label = n.label.replace('"', "'")
        if n.type == "decision":
            rung = n.attrs.get("recommended_rung")
            extra = f" — Rung {rung}" if rung is not None else ""
            lines.append(f'    {nid}["{label}{extra}"]')
        elif n.type == "owner":
            lines.append(f'    {nid}(["{label}"])')
        else:
            lines.append(f'    {nid}[/"{label}"/]')
    arrows = {"owns": "-.->|owns|", "feeds": "-->|feeds|", "depends": "==>|depends|"}
    for e in graph.edges:
        arrow = arrows.get(e.type, "-->")
        lines.append(f"    {safe[e.source]} {arrow} {safe[e.target]}")
    return "\n".join(lines)


def to_graphml(graph: DecisionGraph) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
        '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
        '  <key id="rung" for="node" attr.name="recommended_rung" attr.type="int"/>',
        '  <key id="etype" for="edge" attr.name="type" attr.type="string"/>',
        f'  <graph id="{escape(graph.domain)}" edgedefault="directed">',
    ]
    for n in graph.nodes:
        out.append(f'    <node id="{escape(n.id)}">')
        out.append(f'      <data key="label">{escape(n.label)}</data>')
        out.append(f'      <data key="type">{escape(n.type)}</data>')
        rung = n.attrs.get("recommended_rung")
        if rung is not None:
            out.append(f'      <data key="rung">{rung}</data>')
        out.append("    </node>")
    for i, e in enumerate(graph.edges):
        out.append(
            f'    <edge id="e{i}" source="{escape(e.source)}" '
            f'target="{escape(e.target)}">'
        )
        out.append(f'      <data key="etype">{escape(e.type)}</data>')
        out.append("    </edge>")
    out.append("  </graph>")
    out.append("</graphml>")
    return "\n".join(out)


def export(graph: DecisionGraph, fmt: str = "json") -> str:
    fmt = fmt.lower()
    exporters = {
        "json": to_json,
        "dot": to_dot,
        "mermaid": to_mermaid,
        "graphml": to_graphml,
    }
    if fmt not in exporters:
        raise ValueError(f"Unknown format {fmt!r}. Choose from {sorted(exporters)}.")
    return exporters[fmt](graph)


def _dot_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
