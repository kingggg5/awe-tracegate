# AWE Workspace

Human-gated agent runtime coordination inside the
[AWE TraceGate](https://github.com/kingggg5/awe-tracegate) monorepo.

Workspace turns a saved goal into a narrow, reviewable handoff for an external
Codex, Claude Code, or other runner. It persists goals and discovery briefs,
requires an explicit local approval, exports a typed handoff, and can record
checkpoints. It does **not** invoke a model, run a tool, or issue a TraceGate
decision.

```text
Goal -> Discovery brief -> Select runner and permissions -> Human approval
                                                         |
                                                         v
                                       awe.runtime-handoff.v1
                                                         |
                                                         v
                                      External agent host runs the work
                                                         |
                                                         v
                                Untrusted checkpoint/evidence references
                                                         |
                                                         v
                                      TraceGate verifies held evidence
```

## Run locally

From the repository root:

```bash
npm run workspace:install
npm run workspace:test
npm run workspace:start
```

Open <http://127.0.0.1:8787>. Start the optional TraceGate API separately on
<http://127.0.0.1:8765> when you want the capability probe and evidence-review
link:

```bash
python -m pip install -e ".[api]"
awe-api
```

Configuration is deliberately small:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AWE_WORKSPACE_HOST` | `127.0.0.1` | Loopback bind only |
| `AWE_WORKSPACE_PORT` | `8787` | Workspace HTTP port |
| `AWE_WORKSPACE_DATA_DIR` | `.data` | Owner-local JSON store directory |
| `AWE_TRACEGATE_URL` | `http://127.0.0.1:8765/` | Optional loopback capability probe |
| `AWE_WORKSPACE_WEB_ROOT` | `web` | Static UI directory |

## Implemented runtime contract

- Runners: `codex`, `claude_code`, and `external`.
- Permissions: `read_goal`, `read_evidence_references`, and
  `write_checkpoint`.
- States: `awaiting_approval`, `handoff_ready`, `checkpointed`, and
  `cancelled`.
- Handoff schema: `awe.runtime-handoff.v1`.
- Store schema: `awe.workspace-store.v3`, with migration from the earlier local
  v1/v2 formats.

Granted permissions are descriptive capabilities in the exported handoff. They
do not install connectors, credentials, shell access, browser access, or network
access. The external host remains responsible for its own sandbox and approval
model.

## Local API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Local health and runtime mode |
| `GET/POST` | `/api/goals` | List or save goals |
| `PATCH` | `/api/goals/{id}/discovery` | Record a declared discovery result |
| `GET` | `/api/goals/{id}/export` | Export a discovery brief |
| `GET/POST` | `/api/runs`, `/api/goals/{id}/runs` | List or prepare runtime handoffs |
| `POST` | `/api/runs/{id}/approval` | Approve the exact requested permissions |
| `GET` | `/api/runs/{id}/handoff` | Export the approved typed handoff |
| `PATCH` | `/api/runs/{id}/checkpoint` | Record an approved local checkpoint |
| `POST` | `/api/runs/{id}/cancel` | Cancel the local handoff record |

Mutations require a same-origin request. Host and TraceGate URLs are restricted
to loopback addresses, JSON bodies are bounded, and the store uses restrictive
permissions where supported. This is still a single-user local process, not a
multi-tenant identity or authorization service.

## Trust boundary

Workspace is outside the trusted TraceGate decision core. Goals, approvals,
handoffs, checkpoints, and artifact references are untrusted coordination data.
They cannot become verification evidence or override `PASS`, `REVIEW`, or
`BLOCK`. Use the Python TraceGate CLI/API to validate separately held evidence,
then record any reuse or promotion decision separately.

## Develop

```bash
cd apps/workspace
npm ci
npm run check
npm test
```

Node.js 24 is required. The package has no runtime dependencies and is private;
the public root `awe-tracegate` npm package remains the zero-dependency Skills
installer.
