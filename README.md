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
| [**RungGuard**](services/rungguard/) | ✅ v0.1 | Error Tolerance & Governance control plane. Treats the autonomy rung as a governable object: promotion/demotion approval chains, automatic credential rotation on rung change, blast-radius containment policies enforced at action time, and a rung-tagged audit log. **What the agent was authorized to do at that moment — and enforced automatically.** |

## Quick start

**Decision Atlas** — build the decision map:
```bash
cd services/decision-atlas
pip install -r requirements.txt
python -m decision_atlas serve     # → http://127.0.0.1:8000
```

**RungGuard** — govern the rung lifecycle:
```bash
cd services/rungguard
pip install -e ".[server]"
python -m rungguard serve          # → http://127.0.0.1:8001
```

See the individual READMEs for full docs.

## Repository layout

```
AgenticLadder/
└─ services/
   ├─ decision-atlas/     Service 1: decision discovery & rung recommendation
   └─ rungguard/          Service 2: rung lifecycle governance & policy enforcement
```

Each service is self-contained and independently deployable.
