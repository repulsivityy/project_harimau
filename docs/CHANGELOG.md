# Changelog

All notable changes to Project Harimau will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Fail-Closed Server-to-Server API Authentication (`x-harimau-api-key`) & Proxy Hardening (2026-09-22)**:
  - **Shared Secret & Fail-Closed Lifecycle**: Added `HARIMAU_API_KEY` (`harimau-api-key` in GCP Secret Manager) across `backend/main.py`, `app/src/instrumentation.ts`, `app/src/app/api/[...path]/route.ts`, `deploy.sh`, `cloudbuild-frontend.yaml`, `cloudbuild-backend.yaml`, `push_secrets.sh`, and `.env.example`. Both the FastAPI backend (`lifespan` and HTTP middleware) and the Next.js frontend (`register()` startup hook and runtime proxy route) log a fatal error and immediately terminate the container instance (`os._exit(1)` / `process.exit(1)`) if `HARIMAU_API_KEY` is unconfigured.
  - **Constant-Time Backend Verification & Recon Lockdown**: `backend/main.py` verifies `x-harimau-api-key` using `secrets.compare_digest` on all routes except `/health` and `/` (returning `401 Unauthorized` on mismatch) and disables public schema/recon endpoints (`docs_url=None`, `redoc_url=None`, `openapi_url=None`).
  - **Next.js Catch-All Proxy Hardening (`app/src/app/api/[...path]/route.ts`)**: Replaced full client header forwarding with a strict allowlist (`content-type`, `accept`, `cache-control`, `last-event-id`) so client-supplied headers can never spoof `x-harimau-api-key`, blocked recon/internal path prefixes (`/api/admin/*`, `/api/debug/*`, `/api/diagnostic/*`, `/api/test/*` with `403 Forbidden`), enforced `https://` for non-localhost `BACKEND_URL` targets, and added per-IP sliding-window rate-limiting (`10 requests / 5 minutes`) on `POST /api/investigate`.
- **Harimau Threat Dossier Workbench & Landing Page Redesign (2026-09-22)**:
  - **7-Section Threat Dossier Workbench (`app/src/components/investigation/*`, `app/src/app/investigate/[id]/page.tsx`)**: Migrated the investigation UI to the Threat Dossier layout (`DossierMasthead`, `SpecialistReportsGrid`, `DossierCompanionRail`, `AttackFlowSection`, `TacticalSwimLanes`, `DecoyInsightBanner`, `AppendixIocTable`) with dual view modes (`Threat Dossier` and `Spatial Topology Canvas`), live SSE reasoning stream integration, and entity drawer cross-highlighting.
  - **Threat Dossier Parsing & Normalization (`app/src/lib/dossier-utils.ts`)**: Added deterministic extraction of Executive Summary prose, MITRE ATT&CK swim lanes, decoy/infrastructure pivot banners, DOT diagram blocks, and consolidated Appendix IOC rows with strict URL scheme guards (`http:`/`https:` only) and `normalizeEntityId` parity.
  - **Redesigned Landing Page (`app/src/app/page.tsx`)**: Updated the entry page to match the Harimau Threat Dossier obsidian aesthetic (`#07090E` canvas, top brand bar, predatory tiger emblem `/tiger_logo.png`, 5-level Forensic Intensity selector, `HUNT` command CTA, and Recent Threat Dossiers list).
  - **Isolated Frontend Test Suite (`app/tests/`)**: Added 29 unit and SSR tests (`app/tests/dossier-utils.test.ts`, `app/tests/dossier-components.test.tsx`, `app/tests/fixtures/etherrat-dossier.ts`) kept strictly outside `app/src/`.
- **Supply-Chain Hardening & Runtime Upgrades (2026-09-22)**:
  - **Committed Frontend Lockfile**: `app/package-lock.json` is now tracked in git instead of ignored. This is the only artefact pinning the *transitive* dependency tree with `sha512` integrity hashes; exact top-level pins in `package.json` do not, since each direct dependency pulls dozens of freely-resolving sub-dependencies. Evidence: all 10 advisories currently reported by `npm audit` sit in transitive packages (`brace-expansion`, `browserslist`, `js-yaml`, `@babel/core`, `sharp`, `postcss`, `baseline-browser-mapping`, `@humanfs/node`) — none appear in `package.json`.
  - **`npm ci` Replaces `npm install`**: `app/Dockerfile` now copies `package-lock.json` alongside `package.json` and installs with `npm ci`, so Cloud Build reproduces the exact locked tree and fails loudly on lockfile drift. Previously the image copied only `package.json` and re-resolved every dependency on each build, meaning a breaking upstream minor could break a deploy with no change on our side — the same latent-outage class already documented for the backend `mcp` pin.
  - **Node 22 Active LTS**: Frontend base image moved from `node:20-alpine` to `node:22-alpine`; Node 20 reached end-of-life in April 2026 and no longer receives security patches. `@types/node` pinned to exactly `22.20.4` so type-checking targets the real runtime rather than Node 20. Verified `next@16.2.2` declares `engines.node >=20.9.0`.
  - **Python 3.14 Runtime Alignment**: `backend/Dockerfile` moved from `python:3.11-slim` to `python:3.14-slim`, matching the local development interpreter and eliminating dev/prod drift. Confirmed against PyPI that `asyncpg==0.31.0` and `psycopg-binary==3.3.4` both publish `cp314` wheels, and that `mcp`, `vt-py`, `networkx` and `shodan` are pure-Python. The `python:3.11-slim` syntax-check step in `cloudbuild-backend.yaml` and `cloudbuild-frontend.yaml` was bumped to `python:3.14-slim` to match.
  - **Declared Direct Backend Dependencies & Exact Pinning**: Added explicit exact pins in `backend/requirements.txt` for `aiohttp==3.14.3`, `certifi==2026.7.22`, and `pydantic==2.13.5`, and replaced all remaining version ranges across both `backend/requirements.txt` and `app/package.json` with exact latest compatible versions (`langchain-google-genai==4.4.0`, `langchain-core==1.6.4`, `langgraph==1.2.12`, `langgraph-checkpoint-postgres==3.1.2`, `psycopg[binary]==3.3.6`, `uvicorn==0.53.0`, `networkx==3.7`, `react`/`react-dom` `19.3.0`, `react-markdown` `10.1.0`, `@xyflow/react` `12.11.6`, `tailwindcss`/`@tailwindcss/postcss` `4.3.3`, `@types/d3-graphviz` `3.1.0`). Replaced stale `MAX_DEPTH` and `POLL_INTERVAL` references with `HUNT_ITERATIONS` and `SPECIALIST_TIMEOUT` in `deploy.sh`, `AGENTS.MD`, `terraform/app/main.tf`, and `.env.example`, and removed the redundant Python syntax-check step from `cloudbuild-frontend.yaml`.
  - **Terraform Parity for `HARIMAU_API_KEY`**: `terraform/infra/main.tf` now declares the `harimau-api-key` Secret Manager container, and both Cloud Run services in `terraform/app/main.tf` mount it via `secret_key_ref`. Previously the secret existed only in `deploy.sh`, `cloudbuild-backend.yaml`, `cloudbuild-frontend.yaml`, and `push_secrets.sh` — so a `terraform apply` would have stripped `HARIMAU_API_KEY` from both services and crash-looped them, since each fail-closes (`os._exit(1)` / `process.exit(1)`) when the key is absent. The value is still populated out-of-band by `push_secrets.sh` and never enters Terraform state.
  - **Terraform Parity for Backend Cloud Run Runtime Spec**: `terraform/app/main.tf` was declaring only the image, env vars and Cloud SQL annotation for `harimau-backend`, so a `terraform apply` after any `deploy.sh` run would have silently reverted four runtime settings to Cloud Run defaults. Ported all four from `deploy.sh` L389-397: `run.googleapis.com/cpu-throttling = "false"` (`--no-cpu-throttling`), `resources.limits` of `cpu = "2"` / `memory = "2048Mi"` (`--memory`/`--cpu`), `timeout_seconds = 600` (`--timeout`), and the explicit `command`/`args` override (`uvicorn backend.main:app --host 0.0.0.0 --port 8080`). The CPU annotation is the consequential one: the investigation worker continues running in the background after the HTTP response is returned, and under the default throttled model Cloud Run de-allocates CPU outside request handling, which would stall in-flight hunts. The `command`/`args` values duplicate the image `CMD` in `backend/Dockerfile` and are therefore functionally inert, but `deploy.sh` writes them onto the service as an explicit override, so Terraform must restate them or every plan reports drift. Deliberately not ported: `--allow-unauthenticated` (already covered by the `google_cloud_run_service_iam_policy` `noauth_*` resources), `--add-cloudsql-instances` (already covered by the `cloudsql-instances` annotation), and `--clear-base-image` (a gcloud-CLI-only flag with no Terraform equivalent). The frontend service needs no changes — `deploy.sh` only sets `BACKEND_URL` and the `HARIMAU_API_KEY` secret on it, both already present.
  - **`backend/requirements-dev.txt`**: New file declaring `pytest==9.1.1` and `pytest-asyncio==1.4.0` behind `-r requirements.txt`. `backend/tests/` imports `pytest`, but it was deliberately excluded from `requirements.txt` so test tooling never ships in the production image — which left no declared source of truth for a dev environment.
  - **`.env.example` Alignment**: Added the four live runtime variables the code reads but the template omitted — `VT_APIKEY` (embedded GTI MCP server, distinct from `GTI_API_KEY` used by the direct fast-path client), `GOOGLE_CLOUD_REGION`, `DATABASE_URL`, and `BACKEND_URL`.
  - **`mcp` Pin Documented In Place**: Added a `DO NOT BUMP` comment above `mcp==1.29.0` in `backend/requirements.txt` explaining that it is the last release shipping `mcp.server.fastmcp` (imported by both embedded MCP servers) and that 2.x replaces `FastMCP` with a new `MCPServer` class and drops `stateless_http`. Migration to 2.2.0 tracked as deferred work in `docs/implementation_plan.md` Pillar 7 Milestone 2.
  - **Silent Secret Corruption via `printf` Format-String Injection (2026-09-23)**: All 14 secret writes across `deploy.sh` and `push_secrets.sh` passed the secret *value* as the `printf` **format string** (`printf "$SECRET"`), so any `%` or backslash sequence inside a secret was interpreted rather than emitted. Replaced every site with `printf '%s' "$SECRET"`. Verified against a DSN containing `%73` and `%^`: the old form emitted `postgresql://harimau:pa` followed by space padding — the remainder of the connection string was destroyed. This failed **silently**: `printf` writes its diagnostic to stderr but the pipeline's exit status is `gcloud`'s, so `set -e` never fired and Secret Manager accepted the truncated value. The corruption only surfaced later as an unexplained authentication failure inside Cloud Run.
  - **Cloud SQL Password Charset Not URI-Safe (2026-09-23)**: `deploy.sh` generated the Cloud SQL password from `A-Za-z0-9!@#$%^&*()_+` (74 characters, 18 drawn) and then interpolated it **raw** into the Postgres DSN userinfo at `postgresql://${DB_USER}:${USER_DB_PASS}@/${DB_NAME}?host=/cloudsql/...`. Three of those symbols are URI-reserved in that position: `@` terminates the userinfo component, `#` opens a fragment, and `%` introduces a percent-escape that libpq/psycopg then fail to decode. The probability that an 18-character draw contained at least one of the three is `1 - (71/74)^18` ≈ **53%**, so roughly half of all auto-generated deployments produced a malformed `DATABASE_URL`. Narrowed the charset to `A-Za-z0-9` at both generation sites (bootstrap and password-reset), retaining ~107 bits of entropy. Percent-encoding the password was rejected as the fix because the value is also echoed to the operator's terminal for safekeeping, and an encoded form would not match what they store.
  - **`push_secrets.sh` DB URL Comment Corrected (2026-09-23)**: The commented-out `push_secret "harimau-db-url"` line was annotated "If managed by Terraform, you might not need to push it here", which names the wrong owner. Terraform declares only the empty secret *container*; `deploy.sh` owns the value and writes the Cloud Run Unix-socket DSN (`...@/harimau?host=/cloudsql/PROJECT:REGION:harimau-db`). The `DATABASE_URL` in `.env` is the local TCP form, so uncommenting the line would overwrite the Cloud SQL DSN and break the deployed backend. Comment rewritten to state this explicitly and to keep the line disabled.
  - **`cloudbuild-backend.yaml` Runtime Spec Alignment (2026-09-23)**: Added `--allow-unauthenticated`, `--memory=2048Mi`, `--cpu=2`, `--set-env-vars` (`LOG_LEVEL=DEBUG,HUNT_ITERATIONS=3,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_REGION=asia-southeast1,DETECTION_AGENT_ENABLED=false`), and explicit `--command=uvicorn` / `--args=...` to Step 4 of `cloudbuild-backend.yaml` so all three deployment definitions (`deploy.sh`, `terraform/app/main.tf`, `cloudbuild-backend.yaml`) specify identical Cloud Run service configuration.
  - **Retired Legacy `format_investigation_graph()` Fallback (2026-09-23)**: Removed the 319-line `format_investigation_graph()` reconstruction helper from `backend/utils/graph_formatter.py` and updated `GET /api/investigations/{job_id}/graph` in `backend/main.py` to call `format_graph_from_cache(job_id, job)` exclusively (returning a single-node root IOC seed graph while a job is still running and hydrating `InvestigationCache` from the `investigation_graph` JSONB column once complete).
- **Next.js 16.3.5 Security Upgrade — All Advisories Cleared (2026-09-22)**: Bumped `next` and `eslint-config-next` from `16.2.2` to `16.3.5` and applied the non-breaking `npm audit fix`, taking `npm audit` from **10 advisories (1 critical, 6 high, 2 moderate, 1 low) to 0**.
  - **The `next` advisory covered 25 CVEs**, several directly material to this application's threat model: **unauthenticated remote code execution** in the Image Optimization API via AVIF files (the app serves `next/image` for `/tiger_logo.png` and `/avatar.jpeg`), **unauthenticated RCE on Windows-hosted servers**, at least five distinct **Middleware / Proxy bypass** variants in App Router applications, **server-side request forgery** via rewrites with attacker-controlled destination hostnames and via WebSocket upgrades, **cross-site scripting** in App Router apps using CSP nonces and in `beforeInteractive` scripts, and multiple **cache-poisoning / cache-confusion** issues in React Server Component responses.
  - **Why the proxy bypasses matter here**: the entire `x-harimau-api-key` trust boundary assumes `app/src/app/api/[...path]/route.ts` cannot be circumvented. An App Router routing bypass would let a request reach a path the proxy believes it blocked — including the `/api/admin/*`, `/api/debug/*`, `/api/diagnostic/*` and `/api/test/*` prefixes in `BLOCKED_PATH_PREFIXES`.
  - **Transitive fixes**: cleared `sharp` (libvips/libheif CVEs), `postcss` (XSS via unescaped `</style>`, path traversal via `sourceMappingURL`), `brace-expansion`, `browserslist`, `js-yaml`, `nanoid`, `@babel/core`, `baseline-browser-mapping`, and `@humanfs/node`.
  - **Verified**: production build succeeds on 16.3.5 with all four routes intact (`/`, `/_not-found`, `/api/[...path]`, `/investigate/[id]`), `tsc --noEmit` is clean, `npm ci` confirms lockfile sync, and all 29 frontend tests pass. Peer requirements satisfied — `next@16.3.5` declares `engines.node >=20.9.0` (running `node:22-alpine`) and `react ^19.0.0` (running 19.2.4).
- **Reliability Contract Documentation (2026-09-12)**: Updated the architecture, implementation plan, and dependency graph to document evidence-backed target completion, explicit enrichment/terminal outcomes, typed URL identity handling, persisted specialist evidence, and snapshot-first/cross-instance SSE reconciliation. Historical entries remain unchanged; the current contracts are recorded in the relevant milestones.
- **Durable Specialist Evidence Cache**: Malware and Infrastructure tool outputs, target-specific structured evidence, and relationship provenance are retained in the per-job NetworkX graph. Recursive graph merging preserves simultaneous specialist updates; Lead Hunter planning consumes bounded evidence summaries rather than raw tool payloads. Focused synthetic coverage exercises parallel fan-in and prompt bounding.
- **Evidence-Backed Specialist Target Outcomes**: A selected target now enters `processed_entities` and graph `analyzed_by` only after the *current* specialist attempt explicitly identifies it, supplies substantive target-specific evidence, and has a successful tool call mapped to that target. `target_outcomes` stores minimal latest outcome/evidence metadata per agent and target; timeout, system error, empty final output, tool-error batches, omitted targets, unsupported assertions, and empty evidence remain retryable. Lead Hunter prioritizes retries ahead of new planner work within each specialist cap, and final job metadata preserves lifecycle/gap state for completed hunts.
- **Explicit Specialist Target Lifecycle**: `AgentState` now records `scheduled_entities` separately from `processed_entities`. Triage and Lead Hunter scheduling populate the former, while Malware and Infrastructure record only the targets admitted to their five-/ten-target capped subgraphs in the latter. Lead Hunter convergence now checks processed history, preventing a deferred target from being abandoned merely because it was previously assigned. `tasked_entities` is retained as a compatibility alias for existing persisted checkpoints. Added `test_lead_hunter_requeues_target_deferred_by_specialist_cap`, using only local stubs.
- **Checkpoint-Safe Hunt Recovery**: New investigations persist their complete requested hunt configuration in existing job JSONB metadata (currently `max_iterations`). When a status read finds an orphaned `running` job, the background worker explicitly resumes the saved LangGraph thread with `ainvoke(None, config=...)`; it no longer injects a zeroed initial state that could reset saved iteration and subtask control state. This change intentionally does not add cross-instance task ownership or locking.
- **Rethinking Attack-Chain Roadmap (PRD & Plan)**: Created new architectural PRD & implementation plan in `docs/roadmap_rethinking_attack_chain.md` to replace static relationship strings with open-field agent context tagging and synthetic baseline threat scoring (`70`). Includes Section 6 documenting the interim workaround and step-by-step execution handoff instructions.
- **Active Orchestrator Documentation Comment (§0.4)**: Documented `backend/agents/lead_hunter.py` as the active orchestrator for Project Harimau in a top-level comment to prevent accidental deletion or supersession.
- **Deterministic Graphviz Skeleton (S4-T3)**: New `backend/utils/dot_builder.py` generates the attack-flow `digraph` directly from the NetworkX investigation cache and validates whatever the LLM returns against that graph's own node/edge set, falling back to the skeleton when validation fails. The LLM now *annotates* a supplied skeleton (styling, `subgraph cluster_*` phases, edge-label wording) rather than authoring the diagram freehand. Skeleton node ids are the real normalised entity ids — the previous grounding keyed edges on `_node_label()` display names (`meaningful_name` / `host_name` / `last_final_url`), which could collapse two distinct entities into a single DOT node and contradicted the prompt's own "do not truncate the IOC" rule. Motivation: the frontend's `d3-graphviz` `renderDot()` is async/worker-based, so the `try/catch` around it never fires and malformed DOT silently rendered a blank panel.
- **Shared Diagram Edge Selection (S4-T3)**: `_select_diagram_edges()` in `backend/agents/lead_hunter_synthesis.py` is now the single dedup+cap applied to `_score_edges` output, consumed by both the diagram and the prose edge reference so they can no longer disagree about which edges exist. The `_compute_node_details` → `_compute_high_signal` → `_score_edges` chain is computed once per synthesis instead of twice.

- **Complete Edge Attributes in Synthesis Context (S4-T5)**: `_score_edges` in `backend/agents/lead_hunter_synthesis.py` now records `source_type`, `target_type` and `source_verdict` (it already computed the types for its malware↔infra bridge check and discarded them). The two conflicting edge blocks the LLM used to see — `Key Edges` keyed on entity ids with `target_verdict` + vendor count filtered to 25, and `_build_edge_tuples` keyed on `_node_label()` display names with only the relationship, capped at 40 — are consolidated into a single id-keyed fact table carrying both endpoints' type, verdict and threat score, the relationship, the target's vendor count, and a `high_signal` flag preserving the old `Key Edges` predicate. A GTI threat score that was never supplied now renders `threat_score=unknown` rather than a misleading `0`; this is presentation only, via a new `score_known` flag, and no score is derived or adjusted.

- **Agent Decision Explainability Traces (PR #16)**: Real-time SSE `agent_reasoning` events now surface the actual decision points behind a hunt, not just LLM prose, via `emit_reasoning()` (`backend/utils/transparency.py`):
  - **Deterministic Triage Routing (p1)**: `triage.py`'s `generate_initial_subtasks()` emits a `ROUTING_DECISION` trace listing every initial subtask and, where known, the deterministic qualification rule (`signal_reason`) that qualified the entity — making the non-LLM routing logic auditable in the transparency feed instead of opaque.
  - **Specialist Step-by-Step Reasoning (p2)**: `malware.py` and `infrastructure.py`'s `agent_node` emit a per-iteration trace of either the LLM's own reasoning text or, when it responded with only tool calls, which tools it selected (`[Step N/max] Selecting investigation tools: ...`).
  - **Lead Hunter Convergence & Citation Audit (p3, hardened in `fix(explainability)`)**: `lead_hunter.py` emits a `CONVERGENCE_DECISION` trace at the actual point subtasks are accepted or discarded (moved out of `lead_hunter_planning.py`, since Layer 2/3 checks there can still veto the planner's subtasks and end the hunt instead), and a `CITATION_AUDIT` trace after synthesis reporting the real outcome of `validate_and_annotate()` — verified count, or how many citations were flagged unverified, or that the audit itself failed — rather than a hardcoded success message. `validate_and_annotate()` now returns `(report, validation)` so `lead_hunter.py` can read that outcome; report generation also appends a "🛡️ Citation Integrity Audit" section when every cited IOC is verified.

### Removed
- **Dead Code & Obsolete Artefact Cleanup (2026-09-22)**:
  - **`backend/utils/config.py`**: `load_agents_config()` had zero callers and targeted a `backend/config/agents.yaml` path that does not exist, so every call would have raised `FileNotFoundError`. *(Correction: an earlier revision of this entry also claimed the module was unimportable because `yaml` was absent from `requirements.txt`. That was wrong — `langchain-core` declares `pyyaml<7.0.0,>=5.3.0` unconditionally, so `PyYAML` has always been present in the image. The zero-callers and missing-path reasons stand on their own.)*
  - **`rawGraphRef` (`app/src/app/investigate/[id]/page.tsx`)**: a `useRef` assigned in two places and never read; superseded by the `rawGraphData` state and `effectiveGraphRef`.
  - **`dagre` / `@types/dagre`**: declared dependencies with zero imports; spatial layout is handled by `d3-force`.
  - **Unused Backend Dependencies & System Packages**: Removed `google-cloud-logging==3.16.1` (`logger.py` emits JSON directly to `stdout` via `structlog`), `google-cloud-storage==3.13.0` (Phase 7 roadmap item, zero imports), `python-dotenv==1.2.2` (zero imports), and `graphviz==0.21` from `backend/requirements.txt`, along with `apt-get install graphviz` from `backend/Dockerfile` (`dot_builder.py` generates DOT strings in pure Python and `d3-graphviz` renders in the browser). **Note**: only `google-cloud-logging`, `google-cloud-storage`, and the `graphviz` apt package actually leave the image — `python-dotenv` is still resolved transitively via `mcp` → `pydantic-settings`, so dropping it is declaration hygiene (it is not a direct import) rather than a size saving. `psycopg[binary]` is deliberately **retained** despite having no direct import: `langgraph-checkpoint-postgres` requires bare `psycopg`, and without the `[binary]` extra pip would build from source and need `libpq-dev` in the image.
  - **Dead Functions, Variables, Imports & Commented Blocks**: Removed unused `_gti_score()` in `backend/utils/verdict_engine.py`, unread `location` / `subtasks` locals and commented-out `ChatVertexAI` blocks across `triage.py`, `lead_hunter.py`, `infrastructure.py`, `malware.py`, and `graph_formatter.py`, six unused Python imports (`lead_hunter_planning.py`, `triage.py`, `mcp/client.py`, `mcp/gti/server.py`, `tools/webrisk.py`, `utils/graph_formatter.py`), five unused default `React` imports in `app/src/components/investigation/*.tsx` (`tsc --noUnusedLocals` now exits 0), the byte-identical duplicate `skills/holistic-logic-flow-reviewer/SKILL.md`, and converted the `search_digital_threat_monitoring` docstring in `backend/mcp/gti/tools/files.py` to raw (`r"""`) so `python -W error -m compileall` completes with zero warnings on Python 3.14.
  - **Obsolete Artefacts**: `docker-compose.yml` (non-functional Phase 1 artefact referencing retired `falkordb`, a non-existent root `Dockerfile`, and `streamlit run app/main.py` without `HARIMAU_API_KEY`), `frontend_redesign.md` (design spec superseded by the shipped Threat Dossier components), `prototype/` (static HTML mockup ported into `app/`), `download_reports.py` (one-off script with a placeholder URL and no `x-harimau-api-key` header), five unused `create-next-app` boilerplate SVGs, plus untracked leftovers (`backend/main.py.bak`, `unit_tests/`, the decoupled `detection_agent/` stub, and the Streamlit-era `app/test_old_frontend_backup/`).
  - **Stale Comment (`backend/main.py`)**: replaced a copy-paste artefact (`"""Add this to backend/main.py to diagnose the graph issue."""`) with an accurate section header. The `/api/diagnostic/*`, `/api/test/sse`, and `/history` endpoints were **retained** — they are documented operator tooling, reachable with a valid `x-harimau-api-key`, and only blocked from the public browser proxy.

### Fixed
- **Partial Relationship-Enrichment Failures No Longer Abort a Hunt (2026-09-14)**: `triage_node` returned a terminal failure when *any* requested GTI relationship enrichment failed (e.g. one rate-limited call among 11), even though the rest of root enrichment had already produced a usable graph. It now aborts only when *every* requested relationship fails outright; a partial failure is logged and carried forward as a coverage gap in `enrichment_outcomes` instead.
- **URL Relationship Entities Keyed by GTI's Opaque SHA256 Id (2026-09-14)**: Triage's relationship-parsing loop graphed and tasked `url`-type relationship entities under GTI's raw object id, which for this endpoint's payloads is a SHA256 hash rather than the base64url id `normalise_entity_id` already decodes — producing an unrecognised `gti-url:<sha256>` identity that infrastructure-target matching silently rejected, dropping the lead. The loop now substitutes the entity's own `url`/`last_final_url` attribute as its graph/lifecycle identity and retains GTI's original id as `gti_id` so existing id-based cache lookups still resolve.
- **Graph Merge Could Split a Node in Two (2026-09-14)**: `merge_graphs` normalised the receiving graph's existing node ids without their `entity_type`, while the incoming graph's nodes were normalised with it below — since a node's canonical id can depend on `entity_type` (e.g. URLs), the two sides could disagree for the same entity and silently split it into two nodes on merge. Both sides now normalise consistently.
- **Checkpoint Recovery Never Actually Detected an Unresumable Job (2026-09-14)**: `_has_resumable_checkpoint` checked `if not snapshot`, but `checkpointer.aget_state()` always returns a `StateSnapshot` object — even for a `thread_id` with no persisted checkpoint at all — so that branch could never fire and the function reported every job as resumable. It now also treats a snapshot with empty `values` and empty `next` as unresumable.
- **SSE Subscription Leak on Stream Setup Failure (2026-09-14)**: `GET /api/investigations/{job_id}/stream` registered its subscriber queue via `open_subscription()` before building the initial snapshot; if that lookup raised, the streaming generator whose `finally` normally closes the queue never started running, leaking the subscription. Setup is now wrapped so a failure closes the queue explicitly before re-raising.
- **Specialist Pivot Discovery Had the Same Opaque-Url-Id Gap as Triage (2026-09-14)**: the SHA256-opaque-id fix above was a call-site special case in triage.py's relationship-ingestion loop, not a change to `InvestigationCache.add_entity` itself, so `infrastructure.py`'s three `get_entities_related_to_a_*` tools and `malware.py`'s `get_network_activity` still cached pivot-discovered `url` entities under GTI's raw, undecodable id — confirmed live in production (6 stuck `gti-url:<sha256>` nodes from a real domain's `urls` relationship). A first attempt at a central fix (`add_entity` calling the pre-existing `_canonical_url_node_id` unconditionally) turned out to be inert at those exact call sites — `extract_gti_summary`, which builds their attributes dict, silently dropped the `url`/`last_final_url` fields needed to recover the identity — and separately let attributes override an already-correct id, which could re-key a URL investigation's root node on a harmless spelling difference (e.g. a trailing slash). An Opus 5 review caught both before commit. Fixed by (1) adding `url`/`last_final_url` to `extract_gti_summary`'s captured keys and (2) a new `_resolve_live_url_entity_id` that only falls back to attributes when the caller's id fails to decode at all, and never consults `last_final_url` (a redirect target, not another spelling) on this live path.
- **A Target's Tool Error No Longer Fails Its Whole Batch (2026-09-14)**: `assess_target_outcomes` failed every selected target in a batch if any tool-error envelope appeared anywhere in the specialist's messages, even targets with their own successful, evidence-backed tool call. Removed the batch-wide veto (`_tool_error_seen`) — per-target success is already tracked via tool-call-id provenance in `_successful_tool_targets`. Malware/Infrastructure also now build their failure-path `specialist_attempt` record before the `try` block that can raise, so a cache-construction error can no longer skip recording the failed attempt.
- **Dropped IOC Relationship Nomenclature Alignment (§8.1 workaround)**: Aligned relationship strings from `"dropped"` (singular) to `"dropped_files"` across `backend/agents/malware.py`, `backend/graph/state.py`, and `backend/tests/test_state_merge.py`. Dropped IOCs discovered by `malware_analysis_tool` now match `IMPORTANT_RELATIONSHIPS` in `lead_hunter_synthesis.py` and `dot_builder.py`, receiving `+10` importance score in `_score_edges()`.
- **High-Signal Gate Relaxation for Unscored Nodes (§8.1 workaround)**: Updated `_compute_high_signal()` in `backend/agents/lead_hunter_synthesis.py` so unscored nodes (`not node["score_known"]`) with at least 1 qualifier (such as specialist-discovered dropped files) are admitted into `high_signal_node_ids`.
- **High-Signal Edges Evicted From Synthesis Context (S4-T5)**: consolidating the two edge blocks initially made the fact table share the diagram's unfiltered 40-edge cap, which lost every high-signal edge on a realistic hunt. `_score_edges` sorts `root_adjacent` ahead of everything and derives `node_score` from `max(source_score, target_score)`, so a malicious root hands its own high score to all of its edges — including edges to benign zero-detection CDN domains — and those outranked confirmed-malicious infrastructure several hops out. Measured on a root with 45 benign adjacent edges plus 6 confirmed-malicious distant ones: 0 of the 6 survived. `_select_diagram_edges` now gives high-signal edges first claim on the budget while preserving root-adjacent context for the remainder.
- **An Empty Diagram Passed DOT Validation (S4-T3 follow-up)**: `validate_dot` only checked that the LLM's diagram invented nothing, never that it kept anything, so `digraph AttackChain { }` validated perfectly and the user got a blank diagram — the exact failure the deterministic skeleton exists to prevent. `validate_dot` now takes an optional `required_edges` set and `generate_final_report_llm` passes the skeleton's own edges, so a dropped or truncated diagram falls back to the complete skeleton. Found walking the assembled flow after the tier was complete; the per-task reviews each saw only one commit.
- **URL Entity Ids Broke DOT Validation (S4-T3 follow-up)**: `parse_dot_structure` in `backend/utils/dot_builder.py` stripped `//` comments with a regex, so a URL id (`http://evil.example/p`) had the rest of its line eaten and its quote balance destroyed, leaving fragments that read as invented node ids. The generated skeleton therefore failed to validate against *itself*, so the LLM's annotation was silently discarded and replaced by the bare skeleton on every report whose diagram contained a URL — most real hunts, since `contacted_urls`, `embedded_urls` and `urls` are all in triage's `PRIORITY_RELATIONSHIPS`. Replaced with a quote-aware comment stripper.
- **Attacker-Controlled Labels Could Inject Graph Facts (S4-T5)**: display labels come from `meaningful_name` / `names[0]` / `last_final_url` / `host_name` — i.e. the filename the malware author chose — and were interpolated unescaped into the one-line-per-edge fact table and graph summary. A newline in a label rendered as an extra, fully formed row, letting a sample name fabricate a high-signal edge between entities absent from the graph. Labels are now escaped and flattened.
- **String Threat Scores Could Crash Synthesis (S4-T5)**: a `gti_assessment.threat_score.value` arriving as a string (e.g. `"85"`) was passed through as `str`, reaching `_compute_high_signal`'s `>= 80` comparison and `sorted(key=(score, malicious_count))` and raising `TypeError` — the sibling of the `{"value": None}` crash fixed in 0.6.1. Scores are now numerically coerced, with an unparseable value logged and treated as unknown.
- **SSE Failures No Longer Abort a Hunt (S4-T4)**: `SSEEventManager.emit_event` (`backend/utils/sse_manager.py`) can no longer raise to its caller, and the three emits in `with_sse_events` plus all three `backend/utils/transparency.py` helpers are individually guarded. The `_started` emit previously sat *outside* the node's `try`, so a broadcast failure prevented the node from running at all. The broadcast loop now snapshots the subscriber list, fixing a silent-drop bug: a client disconnecting mid-broadcast shortened the list under the iteration and later subscribers were skipped (measured 1 of 3 delivered). Note the exception-based version of this race is not reachable with today's unbounded `asyncio.Queue` — `put` never suspends — so the guards are insurance against a future `maxsize`.
- **Progress Curve Overrun and Stalled Triage (S4-T4)**: `get_progress_estimate` (`backend/graph/sse_wrappers.py`) divided the 10-90 band by `max_iterations`, but there are `max_iterations + 1` specialist passes (`state["iteration"]` starts at 0 and is only incremented by `lead_hunter`), so specialists at the final iteration computed **103%** — clamped only client-side by `Math.min(pct, 100)`. `triage` also returned 10 for both `started` and `completed` via a dead ternary. Both fixed, and monotonicity plus the 0-100 bound are now enforced centrally by a per-job clamp in `sse_manager` so they also cover the hardcoded percentages emitted from `main.py`.

- **Specialist Tool Timeout & Error Containment (S4-T2)**: Restored the per-tool 20s wall-clock budget and catch-all that `run_tools_parallel` enforced before the `ToolNode` sub-graph refactor, via a new `tool_timeout()` decorator in `backend/utils/agent_utils.py` applied under `@tool` on all 15 specialist tool closures. LangGraph's default `handle_tool_errors` (`_default_handle_tool_errors`) only converts `ToolInvocationError` into a message and re-raises everything else; because each tool awaits `emit_tool_call()` *outside* its own try/except, an SSE broadcast failure (e.g. a browser tab closing mid-hunt) could escape and collapse an entire specialist into a `System Error` verdict.
- **Sub-graph Router Hardening (S4-T2)**: `route_after_agent` in both specialists now uses `getattr(last_message, "tool_calls", None)` and guards missing/empty `messages` instead of assuming the last message is an `AIMessage`.
- **Extra DOT Blocks Reached the Renderer Unvalidated (S4-T3 post-review)**: the frontend keys off the ` ```dot ` language tag, not fence position, and hands *every* such block to `d3-graphviz` — but `extract_dot_block`/`validate_dot`/`replace_dot_block` only ever act on the first one. A second ` ```dot ` block (a restated or partial diagram) therefore reached the renderer having been validated against nothing. New `demote_extra_dot_blocks()` in `backend/utils/dot_builder.py` retags every fence after the first as ` ```text ` — not deleted (the content still has prose value) and not an empty language tag (the frontend renders a language-less fence as inline code, collapsing a whole diagram into one run-on span).
- **DOT Port/Compass Syntax Broke Validation (S4-T3 post-review)**: a port-qualified endpoint (`"a":n -> "b":f:se`) tokenised the port itself as an unrelated bare identifier, so `validate_dot` read it as an invented node reference and silently discarded an otherwise-correct annotation. `parse_dot_structure` now strips the `:port[:compass]` suffix (quote-aware, so colons inside a quoted URL id are untouched) before comparing node ids.
- **Skeleton Labels Could Break Re-emission (S4-T3 post-review)**: `build_dot_skeleton` escaped quotes and backslashes in attacker-chosen display labels (`meaningful_name` / `last_final_url` / `host_name`) but not raw newlines, so a label containing one broke the skeleton's one-statement-per-line shape and made a faithful LLM echo fail validation. Labels are now whitespace-collapsed before escaping, mirroring `_sanitise_label` in `lead_hunter_synthesis.py`.
- **Inconsistent Tool Error Shapes (S4-T2 post-review)**: specialist tools reported failure three different ways depending on which code path caught the exception — a bare exception string, an f-string-built pseudo-JSON object (`f'{{"error": "{e}"}}'`, which produces invalid JSON if the message itself contains a quote), or `tool_timeout`'s `json.dumps({"error": ...})`. All 15 specialist tool closures in `backend/agents/malware.py` / `backend/agents/infrastructure.py` now return `json.dumps({"error": str(e)})` uniformly, so the model always sees one parseable failure envelope.
- **Unpinned `mcp` Was a Live Outage Waiting on the Next Rebuild**: `backend/requirements.txt` was fully unpinned and `Dockerfile` runs a bare `pip install -r requirements.txt` with no lockfile, so every build resolved latest. `mcp`'s latest is now `2.0.0`, which removed `mcp.server.fastmcp` entirely — both `backend/mcp/gti/server.py` and `backend/mcp/shodan/server.py` import it, so the next rebuild would have failed both embedded MCP servers and every hunt would have lost all GTI and Shodan tools. Pinned `mcp==1.29.0` (last version shipping `mcp.server.fastmcp`) plus every other previously-unpinned dependency, verified together via a clean install (full backend imports, `compileall`, the 115-test suite). `langchain-core` (`>=1.5.2,<2`) and `langchain-google-genai` (`>=4.3.2,<5`) are the only two left as bounded ranges rather than exact pins. Migrating to `mcp` 2.x is a separate, not-yet-scheduled task — `stateless_http` was dropped from the replacement `MCPServer` class and needs a decision, not just a rename.

### Changed
- **Subtask-Aware Progress (S4-T4)**: each iteration band's specialist portion is now weighted by `len(state["subtasks"])` instead of a fixed half-band split, so a wide fan-out iteration advances differently from a single-subtask one.
- **Sub-graph Routers Hoisted (S4-T2)**: `route_after_init` / `route_after_agent` moved from the per-invocation MCP-session closure to module scope in `backend/agents/malware.py` and `backend/agents/infrastructure.py`, making them unit-testable.
- **Dead Code Removal (S4-T2)**: Deleted `run_tools_parallel` (zero callers since `9c3327f`) and the commented-out `cap_context_window` helper and its two call sites.

### Documentation
- **Sprint Drift Correction**: `S4-T2` was implemented on `main` in `9c3327f` + `a976cef` (2026-06-04) but never ticked in `sprint_1.md` or `docs/implementation_plan_v2.md`. Both now reflect reality. Note this file still has no entries for the ~30 commits on `main` between 2026-06-04 and 2026-07-21; backfilling them is out of scope for this branch.

## [0.6.5] - 2026-06-04

### Changed
- **Strict Structured Output Migration**: Migrated Malware and Infrastructure specialist agents and Lead Hunter Planning agent to use LangChain's native `with_structured_output()` with strict Pydantic schemas, replacing fragile string-parsing fallbacks.
- **Simplified Agent Iteration Prompt**: Cleaned up `FINAL_ITERATION_PROMPT` in `backend/utils/agent_utils.py` to remove redundant JSON formatting instructions, preventing potential LLM parser confusion.

### Fixed
- **Double LLM Call Prevention**: Restructured specialist agent loops to run the structured LLM parsing exactly once at the end of the reasoning iteration.
- **Indicator-less Target Preservation**: Hardened the state merging logic to prevent dropping targets that do not contain explicit indicator keys.
- **Empty Graph Cache Resilience**: Updated `InvestigationCache` to gracefully handle empty dictionary inputs (`{}`) and avoid initialization crashes.
- **Dead Code and Legacy Workaround Cleanups**: Removed the legacy Vertex AI list block workaround in `lead_hunter_synthesis.py` and pruned the unused `parse_llm_json` helper and dead variables.

## [0.6.4] - 2026-05-30

### Added
- **Canonical Entity-ID Normalisation**: Created robust `_normalise_id()` helper in `backend/utils/graph_cache.py` (strips whitespace, converts to lowercase, safeguards against null/None). Applied across request intake (`POST /api/investigate`) and all cache read/write methods to prevent node duplication and cache misses.
- **Entity Normalisation Unit Tests**: Added dedicated unit test suite `backend/tests/test_entity_normalisation.py` asserting static formatting rules, case invariance during retrieval, and elimination of parallel duplicate edges across mixed casing.

### Fixed
- **Lead Hunter Layer 3 Convergence Fix**: Resolved an early exit convergence failure in `lead_hunter.py` where mixed-case subtask entities failed subset comparisons against lowercased cache nodes (`new_entity_ids.issubset(prev_tasked)`). Both sets are now strictly lowercased before evaluation.
- **Triage Subtask & Super-Bundle Seeding**: Normalised parsed entity dictionaries and subtask entity lists in `triage.py` to prevent mixed-casing leaks from reaching specialist agents.
- **Case-Insensitive UI Root Matching**: Updated `format_graph_from_cache` in `graph_formatter.py` to compare node IDs and root IOCs case-insensitively, ensuring legacy records retain visual root styling (`#FF4B4B`).
- **Case-Insensitive State Reducers**: Hardened `union_lists`, `merge_graphs`, and `push_to_rich_intel` to enforce case-insensitive matching.

## [0.6.3] - 2026-05-30

### Added
- **Graph Caching Deduplication Guard**: Implemented pre-insertion relationship deduplication in `InvestigationCache.add_relationship` (`backend/utils/graph_cache.py`). Intercepts requests where an edge with an identical relationship already exists between source and target, updating metadata in-place and eliminating parallel edge bloat.
- **State Deep Node Merging**: `merge_graphs()` in `backend/graph/state.py` now performs deep merging of node attributes. List attributes like `analyzed_by` perform strict union concatenation to ensure all parallel agent execution traces are preserved.
- **Null-Safety Visual Safeguards**: Hardened `backend/utils/graph_formatter.py` against anomalous non-dictionary GTI assessment structures and explicit `None` edge labels.
- **Graph Merge Unit Tests**: Added full test suite `backend/tests/test_graph_merge.py` verifying deep merging and deduplication flow.

## [0.6.2] - 2026-05-29

### Fixed
- **Specialist Agent Variable Scoping**: Resolved `UnboundLocalError` in Malware and Infrastructure specialist nodes by correctly accessing `iteration` from the job state instead of an undefined local variable.
- **Async TaskGroup Robustness**: Hardened the GTI MCP server's relationship fetching logic. `consume_vt_iterator` now catches and logs API errors (e.g., 404s), preventing a single failed relationship lookup from crashing the entire specialist agent.
- **GTI Parameter Propagation**: Fixed a bug where the `descriptors_only` flag was being ignored in nested relationship calls, ensuring more efficient API usage and reduced token counts.

### Changed
- **State Schema Cleanup**: Removed obsolete fields (`loop_count`, `lead_plan`, `concat_reports`) from `AgentState` to reduce state bloat and complexity.
- **State Reducer Optimization**: Implemented a `union_lists` reducer for `tasked_entities` to prevent duplicate entries and ensure list convergence during parallel agent merges.

## [0.6.1] - 2026-05-29

### Fixed
- **Null Threat Score Safety in Synthesis**: Fixed a potential `TypeError` in `lead_hunter_synthesis.py` where explicit null threat score values (`{"value": None}`) in GTI assessments caused crashes during high-signal node comparisons and sorting. Implemented clean integer fallback mapping to `0`.
- **Lead Hunter Synthesis Unit Tests**: Added a new unit test suite `test_lead_hunter_synthesis.py` covering null and high threat score behaviors.

## [0.6.0] - 2026-05-14

### Added
- **Gemini 3 Migration**: Standardized all agents on the official `ChatGoogleGenerativeAI` SDK using Gemini 3 Flash (Triage) and Gemini 3.1 Pro (Specialists/Synthesis).
- **Deterministic Subtask Routing**: Replaced LLM-driven subtask generation in triage with a robust Python function that maps filtered indicators to appropriate specialist agents.
- **Triage Signal Filtering**: Implemented strict entity filtering in the triage phase (verdict-based or vendor count > 3) to minimize noise and optimize token usage in downstream analysis.
- **Iteration-Aware Specialist Prompts**: Updated Malware and Infrastructure agent prompts to include iteration context, enabling cumulative analysis across multiple hunt rounds.
- **Graphviz Edge Grounding**: Added machine-readable edge tuples to the final synthesis context, ensuring the LLM-generated Graphviz diagrams are grounded in actual relationship data from the NetworkX cache.
- **Confidence Calibration**: Added explicit scoring criteria to the triage prompt to improve the accuracy of the `confidence` field.

### Changed
- **Triage Refactor**: Decoupled triage analysis from task planning. Triage now focuses solely on threat assessment and narrative reporting.
- **Lead Hunter Planning**: Centralized all iterative investigation planning into the Lead Hunter agent.
- **Synthesis Context Optimization**: Removed redundant structured JSON dumps from the synthesis prompt to prioritize the narrative reports and graph structure.

### Fixed
- **Synthesis Diagram Hallucinations**: Fixed an issue where the synthesis LLM would invent relationships not present in the actual investigation data.
- **Triage Metadata Bloat**: Removed stale `subtasks` field from the `triage_analysis` metadata store.

### Added
- **Shared Agent Utilities** (`backend/utils/agent_utils.py`): Extracted common agent logic into a shared module — `parse_llm_json()`, `run_tools_parallel()`, `cap_context_window()`, and `push_to_rich_intel()`. Both specialist agents now import from this module, removing ~80 lines of duplicated code each.
- **threat_score field**: Both Malware and Infrastructure specialist agents now output a `threat_score` field read directly from `gti_assessment.threat_score.value` in the GTI tool response. No derivation or combination — direct passthrough.
- **Cross-agent collaboration instruction**: Infrastructure agent prompt now explicitly instructs the LLM to place file hashes found in `communicating_files` / `downloaded_files` into `related_indicators` with a `File:` prefix, so the Malware agent can pick them up in subsequent iterations.
- **Narrative summary field**: Both specialist agents now produce a 5-paragraph narrative in the `summary` field of their JSON output, giving the synthesis agent richer source material.
- **Context window cap**: `cap_context_window()` prevents unbounded message growth in the agent loop by keeping only the first 2 system messages and the last 10 messages (trimmed to start on an AIMessage to avoid orphaned ToolMessages).
- **Parallel tool execution with timeout**: `run_tools_parallel()` runs all LLM tool calls concurrently via `asyncio.gather` with a per-tool 20-second timeout.

### Fixed
- **Cloud Build Deployment Race Condition**: Fixed an issue in `cloudbuild-backend.yaml` and `cloudbuild-frontend.yaml` where `gcloud run deploy` was executing before the newly built container image was pushed to Artifact Registry, causing deployments to fail with stale image errors. Added explicit `docker push` steps.
- **Malware agent stale tool name**: `get_file_behavior_summary(hash)` → `get_file_behavior(hash)` to match actual MCP tool name.
- **Bare `except: pass` blocks**: Replaced silent exception suppression in both specialist agents with `except Exception as e: logger.warning(...)`.
- **Frontend build — `@types/d3-graphviz` version**: Package only publishes up to `2.6.10`; updated `app/package.json` from `^5.0.0` to `^2.6.10`.
- **Frontend build — graphviz `width`/`height` type error**: Options type requires `number`, not `string`; removed both fields (redundant with `fit: true`).
- **Database Schema**: Reverted `gti_score` column type from `VARCHAR(50)` back to `INTEGER` to enforce strict typing.
- **Data Integrity**: Removed aggressive `"N/A"` string coercion for missing threat scores. Missing scores now safely persist as `NULL` in the database.
- **Frontend Resilience**: Updated the tactical dashboard and modals to gracefully render "Unknown" when encountering `null` or missing threat scores.

## [0.5.0] - 2026-04-09

### Added
- **Next.js Frontend**: Completely rebuilt the user interface using Next.js (App Router, React, Tailwind CSS), replacing the legacy Streamlit application.
- **Real-Time Streaming**: Implemented Server-Sent Events (SSE) to replace the 10-second polling mechanism, providing sub-second, real-time updates for agent tasks and tool calls.
- **Shodan MCP Integration**: Added a Shodan FastMCP server to enrich the Infrastructure Agent with internet exposure data, port scans, and CVE lookups.
- **Configurable Investigation Depth**: Unified loop limiters into a single `max_iterations` state parameter, allowing users to control the depth of each hunt via a frontend slider.

### Fixed
- **Cloud SQL Connectivity**: Added necessary Terraform annotations (`run.googleapis.com/cloudsql-instances`) and Cloud Build flags to ensure the Cloud SQL Auth Proxy socket is correctly injected into the backend Cloud Run container.
- **Frontend API Routing**: Replaced build-time `next.config.ts` rewrites with a runtime catch-all API route (`app/src/app/api/[...path]/route.ts`) so the Next.js container correctly resolves the dynamic backend URL provided by Cloud Run.

## [0.4.0] - 2026-03-23

### Added
- **Cloud SQL Persistence**: Replaced in-memory `JOBS` dictionary with Cloud SQL (PostgreSQL) for durable investigation storage.
- **LangGraph Checkpointing**: Integrated `AsyncPostgresSaver` to persist investigation state snapshots, enabling survival across container restarts.
- **Durable Error Handling**: Hardened background task error handler to ensure failed investigations are always recorded in the database.
- **Advanced Logging**: Enhanced `save_job` error logs with `data_keys` and `metadata_keys` for rapid serialization debugging.

### Fixed
- **State Initialization**: Fixed `initial_state` missing core fields (`iteration`, `loop_count`, `investigation_graph`) that prevented workflow execution.
- **Serialization Safety**: Explicitly excluded non-serializable NetworkX graph objects from database persistence (reconstructed from `rich_intel` for UI).
- **Split-Brain Prevention**: Modified `get_job` to return `None` on database failure instead of falling back to potentially stale in-memory data.
- **Background Failures**: Fixed a race condition where investigations could be silently lost if the initial database save failed.

### Technical Details
- **Deployment**: Integrated `asyncpg` for app data and `psycopg` for LangGraph checkpoints.
- **Resiliency**: Investigations now resume from the last completed node after a crash or scale-down.
- **Integrity**: 22 new unit tests covering persistence flow logic and error boundaries.

## [0.3.1] - 2026-02-07

### Added
- Agent tasks now displayed in collapsible expander in Triage tab for cleaner UI
- Full SHA256 hash display in graph nodes (no truncation)
- Graphviz diagram enforcement for top-to-bottom layout (`rankdir=TB`)
- Future agent roadmap documented: OSINT, Detection Engineering, SOC agents

### Changed
- Increased agent iteration limit from 7 to 10 (`malware_iterations`, `infra_iterations`) for deeper analysis coverage
- **Code Cleanup**: Removed 49 lines of commented-out code across `malware.py`, `infrastructure.py`, `triage.py`
- **Code Cleanup**: Removed 9 outdated `[NEW]` markers from Jan 2026 features (now production-stable)
- **Code Cleanup**: Updated TODO comments to reference roadmap items (Phase 6)
- Graph node labels now show full hashes instead of truncated versions (e.g., `abcde...123ebf` → full SHA256)
- Comment numbering corrections in infrastructure markdown report generator
- Simplified verbose comments in `main.py` for better readability

### Documentation
- Updated `README.md` with "How it works" section
- Added future agent capabilities preview
- Updated `CHANGELOG.md` with recent improvements
- Updated `.gitignore` to exclude `test_*` files

### Fixed
- Infrastructure Agent now successfully processes IP addresses without validation errors
- Both agents robustly handle JSON responses in array or object format
- Subtask status updates now properly mark completed work
- Removed duplicate fallback logic in Infrastructure Agent

## [0.3.0] - 2026-01-30

### Added
- JSON array/object dual-format parsing for both specialist agents
- Comprehensive agent debugging guide (`docs/agent_debugging_guide.md`)
- Regex fallback for target discovery in Infrastructure Agent
- Explicit `entity_id` requirement in Triage Agent subtask generation

### Fixed
- **Critical**: MCP tool argument mapping (`ip` → `ip_address`) preventing IP analysis
- **Critical**: "LLM returned empty content" error via robust fallback logic
- **Critical**: "Extra data" JSON parsing errors when LLM returns arrays
- Missing Infrastructure Specialist reports due to early agent exit
- Duplicate fallback code blocks in agent loops
- Missing subtask status updates in Infrastructure Agent
- Syntax errors from aggressive variable renaming (`reiteration` → `return`)

### Changed
- Increased agent iteration limit from 3 to 7 for comprehensive analysis (subsequently increased to 10 — see v0.3.1)
- Aligned Malware and Infrastructure agent code structures
- Removed Pydantic BaseModel schemas to prevent deployment crashes
- Enhanced error reporting from 500 to 2000 characters
- Improved fallback logic to strictly check for `AIMessage` content

### Technical Details
- **Deployment**: Cloud Run revision `harimau-backend-00139-sln`
- **Region**: asia-southeast1
- **Python Version**: 3.11+
- **Key Dependencies**: LangGraph, LangChain, FastAPI, Streamlit

## [0.2.0] - 2026-01-28

### Added
- NetworkX graph cache for entity relationship tracking
- Malware Specialist markdown report generation
- Infrastructure Specialist agent with network pivoting capabilities
- Graph visualization with tooltips and source-based clustering
- Crowdsourced AI results integration in Triage Agent
- Parallel agent execution with state merge reducers

### Fixed
- Backend 500 errors during parallel agent execution
- Graph centering issues on initial load
- Missing entity relationships in graph visualization
- Triage Agent JSON stability issues

### Changed
- Enhanced Malware Agent with attribution and dropped files analysis
- Improved graph node deduplication logic
- Updated API responses to include `specialist_results`

## [0.1.0] - 2026-01-27

### Added
- Initial Project Harimau V2 implementation
- LangGraph-based investigation workflow
- MCP integration for Google Threat Intelligence API
- Streamlit frontend with investigation graph
- FastAPI backend with async job processing
- Triage Agent with intelligent task decomposition
- Basic Malware Specialist agent

### Technical Stack
- **Frontend**: Streamlit (Python)
- **Backend**: FastAPI + LangGraph + NetworkX
- **LLM**: Google Vertex AI (Gemini 2.5)
- **API**: Google Threat Intelligence (via MCP)
- **Deployment**: Google Cloud Run
- **Graph Storage**: In-memory NetworkX MultiDiGraph

---

## Version Numbering

- **Major** (X.0.0): Significant architectural changes or backwards-incompatible updates
- **Minor** (0.X.0): New features, agent capabilities, or significant improvements  
- **Patch** (0.0.X): Bug fixes, documentation updates, minor tweaks

## Deployment History

| Revision | Date | Version | Notes |
|----------|------|---------|-------|
| 00139-sln | 2026-01-30 | 0.3.0 | JSON array handling, MCP fixes |
| 00137-tx5 | 2026-01-30 | 0.2.5 | MCP argument mapping |
| 00136-2b2 | 2026-01-30 | 0.2.4 | Fallback logic fix |
| 00135-dzs | 2026-01-30 | 0.2.3 | Structural alignment |
| 00134-2rj | 2026-01-29 | 0.2.2 | Pydantic removal |
| 00155-sql | 2026-03-23 | 0.4.0 | Cloud SQL + Checkpointing |
