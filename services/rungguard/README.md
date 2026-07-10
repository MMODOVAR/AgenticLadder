# RungGuard

**Error Tolerance & Governance — autonomy-rung lifecycle control plane**

> *LangSmith and Langfuse tell you what an agent **did**. RungGuard tells you what it was **authorized** to do at that moment — and enforces the boundary automatically.*

RungGuard treats the autonomy rung as a first-class governable object with its own lifecycle: promotion and demotion workflows with role-based approval chains, automatic credential rotation every time the rung changes, blast-radius containment policies that enforce real-time action boundaries, and a rung-tagged audit log that makes every authorization decision auditable and defensible to a regulator.

---

## Autonomy Ladder

| Rung | Name                | Allowed               | Financial cap | Rate limit  |
|------|---------------------|-----------------------|---------------|-------------|
| 0    | Manual              | nothing               | —             | —           |
| 1    | Assisted            | read                  | $0            | 200/min     |
| 2    | Recommended         | read, write (draft)   | $0            | 50 writes   |
| 3    | Supervised          | read, write, comms    | $1 000        | —           |
| 4    | Conditional Auto    | most                  | $50 000       | —           |
| 5    | Full Autonomy       | all                   | unlimited     | —           |

---

## Quick start

```bash
cd services/rungguard
pip install -e ".[server]"

# See the ladder
python -m rungguard ladder

# Start the control plane API + dashboard
python -m rungguard serve
# Open http://127.0.0.1:8001
```

---

## REST API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Control plane dashboard |
| GET | `/api/summary` | Agents, credentials, pending approvals |
| GET | `/api/policies` | Per-rung blast-radius policies |
| POST | `/api/agents` | Register an agent |
| GET | `/api/agents` | List agents |
| GET | `/api/agents/{id}` | Agent detail |
| GET | `/api/agents/{id}/credentials` | Active + historical credentials |
| GET | `/api/agents/{id}/history` | Assignment history + audit trail |
| POST | `/api/agents/{id}/check` | Real-time action authorization |
| POST | `/api/agents/{id}/change-requests` | Submit promotion / demotion |
| GET | `/api/change-requests` | List change requests |
| POST | `/api/change-requests/{id}/approve` | Approve an approval step |
| POST | `/api/change-requests/{id}/reject` | Reject an approval step |
| POST | `/api/change-requests/{id}/cancel` | Cancel a pending request |
| GET | `/api/audit` | Recent audit entries |
| GET | `/api/audit/export` | Full JSONL export |

### Register an agent

```bash
curl -s -X POST http://localhost:8001/api/agents \
  -H "Content-Type: application/json" \
  -d '{"name":"InvoiceBot","owner":"finance-team","initial_rung":1}' | jq .
```

### Check an action

```bash
curl -s -X POST http://localhost:8001/api/agents/<agent-id>/check \
  -H "Content-Type: application/json" \
  -d '{"action":"write_invoice","context":{"amount":500}}' | jq .
```

### Submit a promotion request

```bash
curl -s -X POST http://localhost:8001/api/agents/<agent-id>/change-requests \
  -H "Content-Type: application/json" \
  -d '{"to_rung":3,"requested_by":"alice","justification":"Quarterly review passed"}' | jq .
```

### Approve a step

```bash
curl -s -X POST http://localhost:8001/api/change-requests/<req-id>/approve \
  -H "Content-Type: application/json" \
  -d '{"approver":"bob","approver_role":"domain_owner","notes":"LGTM"}' | jq .
```

---

## Credential providers

| Provider | Cloud / system | Config key |
|----------|---------------|------------|
| `env` | Local env vars / in-memory | `set_env: true/false` |
| `aws` | AWS STS AssumeRole | `region`, `role_prefix`, `account_id` |
| `azure` | Azure Key Vault | `vault_url`, `tenant_id` |
| `gcp` | GCP Secret Manager | `project_id` |
| `vault` | HashiCorp Vault | `url`, `token` |
| `k8s` | Kubernetes ServiceAccount | `namespace`, `sa_prefix` |

All providers work in stub mode (no SDK installed) for development and CI. Pass `aws_sdk: true` (or the equivalent flag) to activate real cloud calls.

---

## Approval chains

| Scenario | Approvers required | SLA |
|----------|--------------------|-----|
| Suspension | CISO | 1 hour |
| Demotion | AI Governance Officer | 4 hours |
| Reinstatement | Domain Owner + AI Governance | 24 hours |
| Promote → rung 3 | Domain Owner | 48 hours |
| Promote → rung 4 | Domain Owner + AI Governance | 48 hours |
| Promote → rung 5 | Domain Owner + AI Governance + CISO | 72 hours |
| Promote → rung 1–2 | Team Lead | 24 hours |

---

## Architecture

```
rungguard/
├── models.py                   # Canonical types (Agent, RungChangeRequest, …)
├── lifecycle/
│   ├── approval.py             # Approval chain definitions + step resolution
│   └── engine.py               # State machine (register → pending → approved → executed)
├── credentials/
│   ├── manager.py              # Revoke-all-then-reissue on every rung change
│   └── providers/              # env · aws · azure · gcp · vault · k8s
├── policies/
│   ├── rules.py                # Per-rung RungPolicy objects (allowed, denied, caps)
│   └── engine.py               # Real-time evaluation + rate limiting
├── audit/
│   └── log.py                  # Append-only rung-tagged log, pluggable external sinks
├── api/
│   ├── store.py                # ControlPlane — wires all components
│   └── app.py                  # FastAPI REST API
└── web/
    └── dashboard.html          # Single-page control plane dashboard
```

---

## Running tests

```bash
cd services/rungguard
pip install -e ".[dev]"
python -m pytest
```

---

## Buyer

**CISO / Head of AI Governance**

RungGuard is the control plane that closes the authorization gap — making AI agent access rights as auditable, governable, and regulatorily defensible as human IAM.
