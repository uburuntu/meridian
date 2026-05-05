# TODO

## Platformization Goal

Meridian should become a structured installation and control API with a CLI client on top. Human terminal output stays polished, but the core product contract should be typed requests, typed results, structured errors, and structured progress events.

Call this contract layer **meridian-core**. The implementation package can be `meridian.core`, but the mental model matters more than the module name: core is the shared brain, the local Engine is the runtime, and every UX surface is a client.

The guiding rule: command modules parse CLI arguments and choose renderers; they should not own business logic, JSON schema, prompts inside core flows, or process exits below the entrypoint.

## Meridian Studio Product Plan

Meridian should grow into a polished local control surface for self-hosters: deploy, watch, recover, and share from one trustworthy UI. This is not a generic admin panel and not just a CLI wrapper.

### Product Bet

- [ ] Build **Meridian Studio** as one contract-driven web UI, first shipped through `meridian ui`.
- [ ] Build **Meridian Engine** as the local-only runtime started by `meridian ui`; it owns SSH, secrets, filesystem state, operation execution, cancellation, and event streaming.
- [ ] Keep **meridian-core** pure: contracts, schemas, validation, planning, redaction, events, and typed operation results.
- [ ] Keep static Studio mode as a plan-only demo/request builder: render workflows, validate input, export `deploy.json`, copy CLI commands, and parse pasted output.
- [ ] Make local Engine mode the real product path for deploy, recovery, fleet management, and operation timelines.
- [ ] Defer Tauri/desktop packaging until localhost Studio works; the desktop app should start the same Engine and render the same Studio UI.
- [ ] Keep mobile companion-only until there is a separate execution strategy; mobile can scan, share, view, pair, and troubleshoot, but should not promise phone-native deploy yet.
- [ ] Keep remote daemon support future-only and gated by a dedicated threat model.

### Must-Win User Journeys

- [ ] First deploy without fear: explain prerequisites, validate VPS/domain/SSH, dry-run, deploy, show progress, and make retry safe.
- [ ] Resume after failure: show what succeeded, what failed, what is safe to retry, and the exact next action.
- [ ] Share access cleanly: create clients, preview recipient pages, show QR/deeplink flows, and guide app-specific import.
- [ ] Verify censorship-resistance: post-deploy checks for open ports, SNI/cert mismatch, Reality reachability, domain/CDN assumptions, and common leak risks.
- [ ] Operate the fleet: show servers, roles, health, clients, relays, drift, and pending changes without requiring YAML fluency.
- [ ] Work offline/in blocked regions: bundled UI, bundled fonts/assets, no telemetry, no CDN dependency, local troubleshooting docs.
- [ ] Preserve power-user trust: every Studio operation can show or copy the equivalent CLI command/request.

### Backlog Lessons

The open issues say Meridian Studio cannot be just a prettier deploy command. They describe a real operations product where users need proof, recovery, topology control, secure handoff, and guided repair. Treat each cluster as a design constraint for meridian-core and Engine contracts.

- [ ] Recovery is product-critical because partial deploys, migrations, backups, offline pulls, missing credential files, teardown ownership, and stale SNI state are normal failure modes, not edge cases. Issues: #30, #42, #48, #53, #70, #71, #72.
- [ ] Topology must become a graph because multi-hop chains, multi-IP nodes, split routing, IPv6, selective outbound paths, relay fan-out, geo-block routing, SNI rotation, and health-based DNS cannot fit a single-server recipe model. Issues: #32, #33, #34, #35, #56, #61, #65, #67, #68.
- [ ] Verification must be evidence, not optimism, because deploy success is not enough in hostile networks; users need tunnel tests, active probing, metrics, real-VM coverage, and clear operator diagnostics. Issues: #36, #37, #52, #55, #57, #63.
- [ ] Client handoff is core product UX because the deployer still fails if recipients cannot import, update, rotate, or disable access safely across real client apps. Issues: #40, #41, #44, #50, #51, #58, #62.
- [ ] Security posture must be explicit because supply-chain verification, process obfuscation, plugin activation, firewall backend choice, and DNS sidecars change the threat model and must not become hidden toggles. Issues: #38, #39, #47, #49, #60, #66.
- [ ] Onboarding must absorb platform friction because Windows/WSL setup, password-only VPS access, custom SSH ports, and nginx/fallback explanations are part of whether users can trust the tool. Issues: #43, #45, #59, #69.
- [ ] AI and automation should be adapters over typed operations because an MCP server is useful only if Engine exposes narrow, audited actions instead of generic shell access. Issue: #64.

### Plan Impact

- [ ] Design Engine as an operation runtime over durable resources, not as a deploy-only HTTP wrapper.
- [ ] Treat `DeployRequest` as one recipe over the future topology graph; do not let it become the whole fleet model.
- [ ] Add first-class resource concepts as the backlog demands them: server, role, route, relay path, client, handoff, backup, probe, metric, secret, plugin, and operation.
- [ ] Make every mutating flow produce a plan, confirmation boundary, operation ID, event stream, terminal envelope, retry guidance, and CLI equivalent.
- [ ] Prioritize deploy + verify + recover as the first Studio proof instead of deploy alone.
- [ ] Keep issue-to-contract traceability: when an issue introduces a durable concept, add or extend a core schema before building UI-only behavior around it.
- [ ] Keep the security model ahead of capabilities: new Engine endpoints need typed permissions, redaction, auditability, and no raw shell/SSH escape hatch by default.

### Architecture Direction

- [ ] Add `meridian.engine` as a localhost-only Engine with HTTP JSON endpoints and SSE event streams.
- [ ] Add `meridian ui` and `meridian ui serve`; bind to `127.0.0.1` only on a random high port.
- [ ] Engine API v1 exposes only typed endpoints: command catalog, schema discovery, workflow discovery, validation, dry-run, start operation, operation status, SSE events, terminal result, and cancel.
- [ ] Engine responses use existing `meridian.output/v1`; SSE streams `meridian.event/v1`.
- [ ] Add `meridian.core.operations` with operation IDs, in-memory operation registry, event replay by sequence, terminal result storage, and best-effort cancellation at step boundaries.
- [ ] Build Studio inside the existing Astro website with adapters: `StaticAdapter`, `LocalEngineAdapter`, `MockAdapter`, future `DesktopAdapter`, and future `MobileCompanionAdapter`.
- [ ] Package built Studio assets with the Python package so `meridian ui` does not require Node at runtime.

### Local Engine Security Bar

- [ ] Treat localhost as hostile: malicious websites, browser extensions, and DNS rebinding are in scope.
- [ ] Use a per-launch 128-bit+ session token; open Studio with the token in the URL fragment only, then exchange it once for a same-origin session cookie.
- [ ] Enforce exact `Host` allowlist and strict `Origin` / `Sec-Fetch-Site` checks for unsafe methods.
- [ ] Disable permissive CORS; v1 does not support cross-origin browser access.
- [ ] Require CSRF protection for every mutating endpoint.
- [ ] Set strict local UI/API headers: CSP, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, and `Cache-Control: no-store` for API responses.
- [ ] Never store long-lived secrets in browser `localStorage`, IndexedDB, URLs, generated contracts, logs, events, screenshots, or telemetry.
- [ ] Redact in core/Engine before data reaches HTTP/SSE; Studio is not a redaction boundary.
- [ ] Do not expose generic shell execution, arbitrary file read/write, raw SSH, or proxy endpoints.

### Generated Contracts and CI

- [ ] Keep Python Pydantic models as the source of truth.
- [ ] Add `scripts/export_contracts.py` to write deterministic JSON Schemas, command catalog, and workflow manifests without spawning the CLI.
- [ ] Add `website/scripts/generate-contract-types.mjs` to generate TypeScript types/manifests from exported contracts.
- [ ] Check generated artifacts into `contracts/meridian/` and `website/src/studio/generated/` with "do not edit" headers.
- [ ] Add CI drift checks: `uv run python scripts/export_contracts.py --check` and `cd website && npm run contracts:check`.
- [ ] Add golden fixtures for deploy dry-run, deploy success envelope, deploy failure envelope, and event stream.

### Implementation Phases

- [ ] Contractgen foundation: export current schemas, command contracts, deploy workflow, and event schema deterministically.
- [ ] Core deploy extraction: finish moving deploy orchestration out of `commands/setup.py` into typed core services; keep Typer, Rich, prompts, `console.fail()`, and process exits outside core.
- [ ] Operation runtime: add operation snapshots, replayable event streams, terminal result cache, and best-effort cancellation.
- [ ] Local Engine: serve Studio assets plus `/api/v1/*` endpoints for workflow/schema/dry-run/start/events/result/cancel.
- [ ] Studio prototype: render deploy workflow, build `DeployRequest`, run dry-run, start deploy, render event timeline, and show final result.
- [ ] Docs and cleanup: add an API/Studio integration page, document preview stability, and document `--events=jsonl` as the process event-stream flag.

### What To Avoid

- [ ] Do not make the Engine shell out to `meridian deploy`; call core services directly.
- [ ] Do not hand-write TypeScript contract types.
- [ ] Do not make Studio forms or generated TypeScript the source of truth.
- [ ] Do not add remote daemon, desktop packaging, or mobile-native deploy before localhost Studio works.
- [ ] Do not build a durable workflow database in v1; in-memory operation state is enough.
- [ ] Do not let Astro/website concerns leak into `meridian.core`.

### Success Criteria

- [ ] A non-expert self-hoster can complete first deploy from Studio without reading the CLI reference.
- [ ] A failed deploy can be retried safely from Studio with clear state and no secret leakage.
- [ ] The same UI runs in static mode with reduced capability and local mode with execution capability.
- [ ] Runtime execution mode requires no external assets, CDNs, fonts, telemetry, or public website availability.
- [ ] UI contracts are generated and validated in CI from Meridian schemas.

## Shared Mental Model

- The interactive CLI wizard is a Meridian client, not the core product. It gathers input, calls meridian-core, then renders a human experience.
- Meridian Studio is another Meridian client. It should be able to plan, execute, and observe deploys through the same core APIs the CLI uses.
- JSON envelopes and event streams are the process boundary for automation and UI clients that shell out to `meridian`. A supported Python API can expose the same request/result/event objects directly.
- Public meridian-core contracts should use Pydantic v2 models where validation, `model_dump_json()`, `model_validate*()`, or `model_json_schema()` helps UI/client integration. Keep Pydantic at API boundaries; internal execution objects do not need to become Pydantic by default.
- Cluster config is part of the API, not just a local implementation detail. Core should accept desired topology from disk, memory, or another client-provided source, then persist through the configured store.
- Core should expose recipes for normal users and lower-level operations for advanced users. Advanced SSH-capable operations are allowed, but must be explicit, auditable, redacted, and clearly dangerous.
- Idempotent operations are the recovery model for v1. If a UI wants resumability, it can track operation IDs/events and rerun safe recipes; core does not need durable workflow state yet.
- Topology is a fleet of servers with roles and capabilities. A server may be a panel host, exit node, relay node, or multiple roles over time.
- Routing policy is part of topology. Example future shape: `.ru` traffic exits through a Russia-zone exit, while non-RU traffic goes abroad; multiple relays can fan into one or more exits.

## Execution Mandate

- [ ] Build toward a CLI/API that is impressive enough to show to UI-client authors as an integration contract, not just an internal refactor.
- [ ] Prefer refactoring to stronger module boundaries before adding one-off feature behavior.
- [ ] Make Meridian feel built from legos: each piece has a clear contract, focused tests, and minimal hidden global state.
- [ ] Commit each significant architectural step separately.
- [ ] Review platformization work with distinct perspectives: architecture, product/API contract, regression/security, and a Joker reviewer who is expected to challenge assumptions hard.
- [ ] Repeat review/fix loops until the core surfaces feel disciplined, documented, and ready for new clients.
- [ ] Keep user-facing docs and CLI text aligned with the API contract as part of every platformization change.

## Product Assumptions

- Text output remains the default UX.
- `--json` means one final machine-readable result envelope on stdout, everywhere.
- `--events=jsonl` means machine-readable event stream on stderr for long-running operations, including deploy/apply.
- Human logs/progress go to stderr or are suppressed in API modes.
- JSON/API modes are non-interactive by default. Missing input returns a structured user error.
- Secrets are never emitted in JSON, JSONL, errors, event data, command metadata, or logs.
- Current process exit codes stay compatible for now; JSON `status` and `error.category` carry richer meaning.

## Open Product Questions

- [ ] Is `plan` exit code `2` for changes-pending sacred, even though `2` also means user errors elsewhere?
- [ ] Which commands are contract-stable in v1, and which stay best-effort/internal until later?
- [ ] Should API fields optimize for shell/JQ consumers, Python SDK consumers, or both equally?
- [ ] What exact advanced SSH operations should be supported as public escape hatches, and what guardrails do they need?
- [ ] Which routing policies are v1 scope: per-domain category, per-country domain lists, per-node default egress, or all of these?
- [ ] Should role terminology in config become explicit now (`panel`, `exit`, `relay`) or wait until topology work begins?

## Target Architecture

- [ ] `meridian.core`: product use cases and request/result models; no Typer, Rich, `print`, or `typer.Exit`.
- [ ] `meridian.core.models`: stable Pydantic models for envelopes, errors, events, plans, inventory, clients, servers, roles, routes, deployment results, and provision results.
- [ ] `meridian.core.services`: service functions such as `get_fleet_inventory()`, `compute_apply_plan()`, `apply_desired_state()`, `deploy_server()`, `assign_role()`, `deploy_relay()`, `add_client()`.
- [ ] `meridian.core.renderers`: JSON, JSONL, and Rich/text renderers over the same result/event objects.
- [ ] `meridian.core.reporters`: event sink abstraction for provisioners, reconciler execution, SSH diagnostics, warnings, and prompts.
- [ ] `meridian.cli`: Typer argument parsing, request construction, renderer selection, prompt collection, and exit-code mapping only.
- [ ] Keep adapters explicit: Remnawave API, SSH, filesystem cluster store, cloud providers, and template rendering.

## Topology Model

- [ ] Model the fleet around servers with roles, not separate mental categories for "node" and "relay".
- [ ] Represent roles explicitly: `panel`, `exit`, `relay`, and future role extensions.
- [ ] Allow one server to carry multiple roles when safe.
- [ ] Preserve today's simple single-server and node-only flows as recipes over the role model.
- [ ] Support star topology: many relays forwarding to one exit.
- [ ] Support multi-exit topology: relays and clients can select different exits based on policy.
- [ ] Add route policy model for domain/category/country split routing, including RU-local exit for `.ru` or Russian content while non-RU traffic exits abroad.
- [ ] Keep relay attachment explicit: relay role has one or more upstream exit targets and health state.
- [ ] Keep server inventory stable enough for UI graph rendering.
- [ ] Add topology planner tests for single-node, star relay, multi-relay, and RU-local-exit scenarios.

## JSON Envelope v1

- [x] Define `meridian.output/v1` for migrated non-streaming JSON results.
- [x] Standardize top-level fields:
  - `schema`
  - `meridian_version`
  - `command`
  - `operation_id`
  - `started_at`
  - `duration_ms`
  - `status`
  - `exit_code`
  - `summary`
  - `data`
  - `warnings`
  - `errors`
- [x] Use `status` values: `ok`, `changed`, `no_changes`, `failed`, `cancelled`.
- [x] Make `data` command-specific and stable by command.
- [x] Make `summary` structured enough for dashboards, not only prose.
- [x] Use one shared warning/error object shape in both `warnings` and `errors`.
- [x] Add serializer unit tests for envelope success, failure, JSONL, and redaction cases.
- [x] Keep stdout/stderr rendering outside `meridian.core`; core owns models and serialization primitives only.
- [x] Add command-specific envelope schemas for the first migrated commands.
- [x] Add a command contract catalog that maps migrated commands to envelope/data schemas, statuses, flags, and exit-code meanings.
- [x] Add source availability fields so partial fleet failures do not disappear in JSON.
- [x] Make command envelope schemas accept both typed success data and empty failed/cancelled data.
- [x] Validate command envelope status/data/error consistency in Pydantic models.
- [x] Strip secret URL paths from fleet API output; expose origins and booleans, not bearer-style routes.
- [x] Add typed `apply --json` final-result contract with per-action execution status.
- [x] Expose plan display order vs apply execution order so UI clients do not infer execution from list position.
- [ ] Add golden JSON fixtures for the first migrated commands.

Example:

```json
{
  "schema": "meridian.output/v1",
  "meridian_version": "4.x.x",
  "command": "fleet.inventory",
  "operation_id": "01J...",
  "started_at": "2026-05-04T21:00:00Z",
  "duration_ms": 128,
  "status": "ok",
  "exit_code": 0,
  "summary": {
    "text": "2 nodes, 1 relay, 0 pending",
    "changed": false
  },
  "data": {},
  "warnings": [],
  "errors": []
}
```

## Error Model v1

- [x] Define `MeridianError` with:
  - `code`
  - `category`
  - `message`
  - `hint`
  - `retryable`
  - `exit_code`
  - `details`
  - `cause`
- [x] Use categories: `user`, `system`, `bug`, `cancelled`.
- [ ] Replace deep `console.fail()` calls with structured exceptions/results below CLI entrypoints.
- [ ] Keep CLI entrypoints responsible for rendering human errors and mapping to `typer.Exit`.
- [ ] Add JSON-mode error tests for user, system, bug, and cancelled paths.
- [x] Add initial redaction tests for API tokens, passwords, JWTs, and database URLs.

Example:

```json
{
  "code": "MERIDIAN_PANEL_UNREACHABLE",
  "category": "system",
  "message": "Cannot reach panel API",
  "hint": "Check panel connectivity and run meridian doctor.",
  "retryable": true,
  "exit_code": 3,
  "details": {},
  "cause": {
    "type": "RemnawaveNetworkError"
  }
}
```

## JSONL Event Model v1

- [x] Define `meridian.event/v1` for streaming progress primitives.
- [x] Standardize fields:
  - `schema`
  - `operation_id`
  - `seq`
  - `time`
  - `level`
  - `type`
  - `phase`
  - `resource`
  - `message`
  - `data`
- [ ] Add event types:
  - `command.started`
  - `command.completed`
  - `plan.computed`
  - `plan.action.started`
  - `plan.action.completed`
  - `plan.action.failed`
  - `plan.action.skipped`
  - `provision.step.started`
  - `provision.step.completed`
  - `ssh.command.completed` for verbose/debug streams only
  - `state.loaded`
  - `state.saved`
  - `warning`
  - `error`
- [ ] Ensure the final JSONL event includes the same final envelope produced by `--json`.
- [x] Guarantee monotonic `seq` in the core event stream primitive.
- [ ] Preserve per-resource event order.
- [ ] Add JSONL tests for provision step start, completion, failure, and redaction.
- [x] Export JSON Schemas for public meridian-core contracts so UI clients can validate integrations.

Example:

```json
{
  "schema": "meridian.event/v1",
  "operation_id": "01J...",
  "seq": 12,
  "time": "2026-05-04T21:00:02Z",
  "level": "info",
  "type": "provision.step.completed",
  "phase": "provision",
  "resource": {
    "kind": "node",
    "id": "198.51.100.10"
  },
  "message": "Install Docker",
  "data": {
    "status": "changed",
    "duration_ms": 1832
  }
}
```

## CLI Contract

- [ ] Support both global and command-local JSON flags for migrated commands:
  - `meridian --json fleet inventory`
  - `meridian fleet inventory --json`
- [x] Reject global `--json` for commands that are not migrated to the envelope contract yet.
- [ ] Add `--events=jsonl` to long-running commands: `apply`, `node add`, `relay deploy`, `teardown`, and likely `doctor`; deploy already has the preview process API.
- [ ] Add `--no-input` and make `--json` imply it unless a command explicitly documents otherwise.
- [ ] Treat the interactive wizard as a client of meridian-core; it does not need a special JSON mode as long as the underlying core calls are structured.
- [ ] Audit every public command for JSON support:
  - `deploy`
  - `apply`
  - `plan`
  - `client add/show/list/remove`
  - `node add/list/check/remove`
  - `relay deploy/list/remove/check`
  - `fleet status/inventory/recover`
  - `server add/list/remove`
  - `preflight`
  - `probe`
  - `test`
  - `doctor`
  - `teardown`
  - `recover`
- [ ] Add CLI matrix tests proving every public command either supports JSON flags or is explicitly excluded.
- [ ] Extend docs validation so CLI reference JSON flags cannot drift from Typer registration.

## Migration Plan

### Phase 1: Contract Foundation

- [x] Add `meridian.core.models` with Pydantic output envelope, event, summary, and error models.
- [x] Add JSON and JSONL serializer helpers with stable key ordering.
- [x] Add `operation_id` generation and monotonic event sequence support.
- [x] Add redaction utilities for JSON and JSONL output.
- [ ] Add golden contract tests for envelope and error rendering.

### Phase 2: Read-Only Commands First

- [x] Move `fleet inventory` result construction into a service returning a typed result.
- [x] Render `fleet inventory` text and JSON from that typed result.
- [x] Move `fleet status` result construction into a service returning a typed result.
- [x] Render `fleet status` text and JSON from that typed result.
- [x] Move `client list` and `client show` to service/result/renderer boundaries.
- [x] Preserve existing human output while adding envelope JSON.
- [ ] Keep config loading/saving behind a store interface so UI clients can supply config through memory or files.

### Phase 3: Plan and Apply

- [x] Convert `plan --json` to the shared envelope everywhere; v4 does not need a legacy JSON mode.
- [x] Expose plan actions as typed API result objects.
- [x] Add semantic plan action fields (`operation`, `resource_type`, `resource_id`, `phase`, `requires_confirmation`) so clients do not infer behavior from display symbols.
- [x] Populate `change_set` for node and relay update plans.
- [x] Mark destructive relay replacements explicitly in plan JSON (`operation: "replace"`).
- [ ] Add `execute_plan()` reporter hooks for action start/completion/failure.
- [x] Add `apply --json` final envelope.
- [ ] Add `apply --events=jsonl` event stream.
- [x] Make `apply --json` non-interactive; callers must pass explicit `yes` and drift decisions.
- [ ] Ensure prompts are CLI-only across every remaining API-capable command.
- [ ] Redesign apply execution phases toward preflight -> create/enable -> switch/verify -> delete/disable, with operation journaling instead of destructive-first deletes.

### Phase 4: Provisioning Events

- [x] Add optional reporter to `Provisioner.run()`.
- [x] Emit `provision.step.started` and `provision.step.completed` from `Provisioner`.
- [ ] Render existing Rich progress from provision events.
- [ ] Keep `StepResult` as the compact step contract.
- [ ] Decide whether redacted `CommandResult` data is included in verbose JSONL only.
- [ ] Add system lab or E2E smoke coverage for JSONL deploy output.

### Phase 5: Imperative Command Extraction

- [ ] Extract `deploy` orchestration from `commands/setup.py` into core service functions.
- [ ] Extract `node add` orchestration into core service functions.
- [ ] Extract `relay deploy` orchestration into core service functions.
- [ ] Extract client add/remove operations into core service functions.
- [ ] Extract recover operations into core service functions.
- [ ] Keep CLI prompts, wizard copy, Rich panels, and confirmation handling in command/renderer layers.
- [ ] Expose advanced lower-level operations with explicit consent and audit events: SSH connectivity check, fact collection, package ensure, service ensure, file write, command run, role deploy, role remove.

### Phase 6: Documentation and Compatibility

- [ ] Add website docs page: API / Automation Contract.
- [ ] Document JSON envelope, JSONL event stream, errors, exit codes, non-interactive behavior, redaction guarantees, and compatibility policy.
- [x] Add CLI schema discovery/export for meridian-core contracts.
- [x] Add CLI command contract discovery/export for migrated meridian-core commands.
- [ ] Add examples with `jq` for `plan`, `apply`, `deploy`, and `fleet status`.
- [ ] Document which fields are stable and which are diagnostic/best-effort.
- [ ] Add CHANGELOG notes whenever API schemas add fields or change behavior.

## Exit Codes

- [ ] Preserve current process codes initially:
  - `0`: success
  - `1`: bug/unexpected
  - `2`: user/config problem, plus `plan` changes-pending for compatibility
  - `3`: system/infrastructure problem
- [ ] Make JSON `status`, `summary.changed`, and `error.category` authoritative for machine interpretation.
- [ ] Add explicit cancelled handling and avoid accidental success on user cancellation.
- [ ] Revisit exit-code cleanup only at a future major boundary.

## Risks

- [ ] `console.fail()` currently exits from deep command flows and blocks API reuse.
- [ ] Global JSON/quiet state in `console.py` is not composable for embedded API callers.
- [ ] `commands/setup.py` is large and imperative; extraction must be incremental.
- [ ] Parallel apply needs deterministic event ordering without hiding concurrency.
- [ ] More JSON surface area increases secret leakage risk unless redaction is centralized.
- [ ] Changing `plan --json` may break current scripts; acceptable for v4, but release notes must call it out clearly.
- [ ] Rich progress must remain polished when moved behind event renderers.
- [ ] Advanced SSH escape hatches can become unsafe if they bypass redaction, idempotency, or audit events.
- [ ] Current config names distinguish nodes and relays; the product model is moving toward servers with roles, so migration needs careful wording.

## Near-Term First Slice

- [x] Build `meridian.core.models` with Pydantic `OutputEnvelope`, `MeridianError`, and `Event`.
- [x] Build shared `emit_json()` and `emit_jsonl()` renderers.
- [ ] Add command-local `--json` support to all read-only commands.
- [x] Migrate `fleet inventory` to service/result/renderers.
- [x] Migrate `plan` to shared envelope and add contract tests.
- [x] Add JSON error rendering at CLI entrypoint boundary.
- [x] Add redaction tests before expanding JSON surface area further.
