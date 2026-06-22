# Decision Atlas

> The map you point your agents at.

Decision Atlas is a **discovery engine** that crawls your existing workflow
systems, ticketing platforms, approval chains, and audit logs to auto-build a
**live map of every decision made across the enterprise** — who owns it, what
data feeds it, what "correct" looks like, and a recommended **target autonomy
rung**.

Instead of running workshops with sticky notes, a domain owner opens a dashboard
and sees their decisions *already plotted*, ready to annotate and approve.

It is the **first service of the [AgenticLadder](../../README.md) platform**.
Everyone else sells you tools to *build* agents. Decision Atlas builds the map of
**what to point them at** — the input to agentic transformation that nobody else
productizes.

---

## Why this exists (the wedge)

| The market | Decision Atlas |
| --- | --- |
| Sells agent frameworks, orchestration, copilots | Sells the **map of decisions** to automate |
| Bought *after* you pick a framework | Bought **before** any framework — by the CTO / Head of EA |
| Starts with "what can the tool do?" | Starts with "**what decisions do we even make, and which are ready?**" |

**Buyer:** Chief Transformation Officer / Head of Enterprise Architecture.

## Core features

1. **Automated decision discovery** — connectors normalize events from any
   source system into a canonical model, then cluster them into distinct
   decisions grouped by business domain.
2. **Ownership & criteria annotation UI** — a dashboard where domain owners
   confirm the owner, define what "correct" looks like, tune signals, and
   approve.
3. **Rung-recommendation engine** — an explainable model that recommends a
   target autonomy rung for every decision, with a full rationale.
4. **Exportable "decision graph" per domain** — JSON, Graphviz DOT, Mermaid,
   and GraphML for any downstream EA / visualization tool.

## Works across any cloud, language, or application

The whole design hinges on a **canonical, source-agnostic data model**. Every
connector adapts one source system into a stream of `DecisionEvent`s; everything
downstream (clustering, rung scoring, graph export) is source-agnostic.

Built-in connectors:

| Connector | Adapts | Examples |
| --- | --- | --- |
| `audit_log` | Any structured JSON/JSONL log with a field **mapping** | AWS CloudTrail, GCP Audit Logs, Azure Activity Log, DB tables, app event streams |
| `jira` | Ticketing with transition history | Jira, GitHub Issues, Azure DevOps, Linear |
| `approval` | Approval / ITSM records | ServiceNow, custom approval tables |
| `workflow` | Workflow / BPM execution traces | Airflow, Temporal, Camunda, Step Functions |

The universal `audit_log` connector means onboarding a new system is usually a
**config change, not code** — just describe where the fields live:

```json
{
  "type": "audit_log",
  "name": "cloudtrail-prod",
  "path": "events.jsonl",
  "mapping": {
    "id": "eventID", "decision_key": "eventName", "timestamp": "eventTime",
    "actor": "userIdentity.arn", "outcome": "responseElements.status",
    "input_fields": "requestParameters", "domain": "recipientAccountId"
  }
}
```

Adding a brand-new connector is one class — see
[`connectors/base.py`](decision_atlas/connectors/base.py).

## The autonomy ladder

The rung engine recommends a target on this six-rung ladder:

| Rung | Name | The agent… | The human… |
| ---: | --- | --- | --- |
| 0 | Manual | (nothing) | decides & acts |
| 1 | Assisted | informs & surfaces data | decides |
| 2 | Recommended | proposes an action | approves each action |
| 3 | Supervised | acts automatically | reviews after the fact |
| 4 | Conditional Autonomy | acts within guardrails | handles only escalations |
| 5 | Full Autonomy | owns the decision | monitors KPIs only |

### How a rung is recommended

Two forces, both fully explainable:

* **Readiness** — a weighted blend of *enabler* signals (volume, reversibility,
  data availability, determinism, historical consistency) maps to a **base rung**.
* **Risk ceiling** — *impact* (blast radius) and *regulatory sensitivity* impose
  a **hard cap**.

The recommendation is `min(base, ceiling)`, plus a **confidence** score driven by
how much real evidence (vs. heuristic defaults) backed the signals. Each signal
carries its **provenance** (`derived` / `default` / `annotated`) so owners know
exactly what to trust and what to confirm.

## Quick start

```bash
cd services/decision-atlas

# 1. Run discovery on the bundled multi-source sample data (no deps needed)
python -m decision_atlas discover

# 2. See the autonomy ladder
python -m decision_atlas ladder

# 3. Export a domain's decision graph
python -m decision_atlas export --domain Finance --format mermaid

# 4. Run the dashboard + REST API (needs: pip install -r requirements.txt)
python -m decision_atlas serve
#   → open http://127.0.0.1:8000
```

### Use it as a library

```python
from decision_atlas import DiscoveryEngine, build_graph, export

engine = DiscoveryEngine.from_config({
    "sources": [
        {"type": "jira",       "path": "tickets.json"},
        {"type": "audit_log",  "path": "cloudtrail.jsonl",
         "mapping": {"decision_key": "eventName", "actor": "userIdentity.arn"}},
    ]
})
domains = engine.discover()
for d in domains:
    for dec in d.decisions:
        print(dec.name, "→ Rung", dec.recommendation.recommended_rung)
    print(export(build_graph(d), "mermaid"))
```

## REST API

| Method & path | Purpose |
| --- | --- |
| `GET /` | Annotation dashboard (single-page app) |
| `GET /api/ladder` | The autonomy ladder definition |
| `POST /api/discover` | Crawl sources (`{}` uses bundled sample config) |
| `GET /api/summary` | Counts + recommended-rung histogram |
| `GET /api/domains` | List domains |
| `GET /api/domains/{domain}/decisions` | Decisions in a domain |
| `GET /api/decisions/{id}` | One decision |
| `POST /api/decisions/{id}/annotate` | Set owner/criteria/signal overrides/target |
| `POST /api/decisions/{id}/approve` | Owner sign-off |
| `GET /api/domains/{domain}/graph?format=json\|dot\|mermaid\|graphml` | Export the decision graph |

## Architecture

```
decision_atlas/
├─ models.py            Canonical, source-agnostic data model (stdlib only)
├─ connectors/          Source adapters — the cross-cloud/app layer
│   ├─ base.py          Connector ABC + plugin registry
│   ├─ audit_log.py     Universal field-mappable connector
│   ├─ jira.py / approval.py / workflow.py
├─ discovery/           Crawl → cluster → derive signals
│   ├─ engine.py
│   └─ signals.py
├─ rung/                Autonomy ladder + recommendation engine
│   ├─ ladder.py
│   └─ engine.py
├─ graph/               Decision-graph builder + exporters
│   ├─ builder.py
│   └─ export.py        json / dot / mermaid / graphml
├─ api/                 FastAPI app + in-memory store (optional dep)
└─ web/dashboard.html   Annotation & approval UI
```

**The core engine has zero runtime dependencies** (pure standard library), so it
embeds anywhere. FastAPI/uvicorn are only needed for the API + dashboard.

## Tests

```bash
cd services/decision-atlas
python -m unittest discover -s tests -t .   # stdlib, no install needed
# or, with dev extras installed:
pytest
```

## Roadmap (next services on the ladder)

Decision Atlas produces the map. Subsequent AgenticLadder services help you
*climb* it — guardrail design, agent scaffolding, and rung-by-rung promotion
with evidence — all anchored to the decisions discovered here.
