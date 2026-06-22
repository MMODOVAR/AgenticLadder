# AgenticLadder

**The platform for agentic transformation — start with the map, then climb.**

Every enterprise rushing into AI agents hits the same wall: they buy frameworks,
orchestration, and copilots before they can answer the most basic question —
*which decisions do we actually make, who owns them, and which are ready to hand
to an agent?* AgenticLadder fills that gap, then guides each decision up an
**autonomy ladder** from manual to fully autonomous, safely and with evidence.

## The autonomy ladder

| Rung | Name | The agent… | The human… |
| ---: | --- | --- | --- |
| 0 | Manual | (nothing) | decides & acts |
| 1 | Assisted | informs & surfaces data | decides |
| 2 | Recommended | proposes an action | approves each action |
| 3 | Supervised | acts automatically | reviews after the fact |
| 4 | Conditional Autonomy | acts within guardrails | handles only escalations |
| 5 | Full Autonomy | owns the decision | monitors KPIs only |

## Services

| Service | Status | What it does |
| --- | --- | --- |
| [**Decision Atlas**](services/decision-atlas/) | ✅ v0.1 | Crawls workflow systems, ticketing, approval chains, and audit logs to auto-build a live map of every enterprise decision — owner, inputs, success criteria, and a recommended target autonomy rung. **The map you point your agents at.** |

> More services will help you *climb* the ladder Decision Atlas maps — guardrail
> design, agent scaffolding, and rung-by-rung promotion.

## Quick start

```bash
cd services/decision-atlas

# Run discovery on bundled multi-source sample data (no dependencies needed)
python -m decision_atlas discover

# Launch the dashboard + API
pip install -r requirements.txt
python -m decision_atlas serve     # → http://127.0.0.1:8000
```

See the [Decision Atlas README](services/decision-atlas/README.md) for full docs.

## Repository layout

```
AgenticLadder/
└─ services/
   └─ decision-atlas/     First service: the discovery engine
```

Each service is self-contained and independently deployable.
