# TODO

## Platformization Goal

Meridian should become a structured installation and control API with a CLI client on top. Human terminal output stays polished, but the core product contract should be typed requests, typed results, structured errors, and structured progress events.

Call this product layer **meridian-core**. The implementation package can be `meridian.core`, but the mental model matters more than the module name: core is the engine, and every UX surface is a client.

The guiding rule: command modules parse CLI arguments and choose renderers; they should not own business logic, JSON schema, prompts inside core flows, or process exits below the entrypoint.

## Shared Mental Model

- The interactive CLI wizard is a Meridian client, not the core product. It gathers input, calls meridian-core, then renders a human experience.
- A future UI is another Meridian client. It should be able to plan, execute, and observe deploys through the same core APIs the CLI uses.
- JSON/JSONL is the process boundary for automation and UI clients that shell out to `meridian`. A supported Python API can expose the same request/result/event objects directly.
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
- `--jsonl` means machine-readable event stream on stdout for long-running operations, including deploy/apply.
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

- [ ] Support both global and command-local JSON flags everywhere:
  - `meridian --json fleet inventory`
  - `meridian fleet inventory --json`
- [ ] Add `--jsonl` to long-running commands: `deploy`, `apply`, `node add`, `relay deploy`, `teardown`, and likely `doctor`.
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
- [ ] Move `fleet status` result construction into a service returning a typed result.
- [ ] Render `fleet status` text and JSON from that typed result.
- [ ] Move `client list` and `client show` to service/result/renderer boundaries.
- [ ] Preserve existing human output while adding envelope JSON.
- [ ] Keep config loading/saving behind a store interface so UI clients can supply config through memory or files.

### Phase 3: Plan and Apply

- [x] Convert `plan --json` to the shared envelope everywhere; v4 does not need a legacy JSON mode.
- [ ] Expose plan actions as typed API result objects.
- [ ] Add `execute_plan()` reporter hooks for action start/completion/failure.
- [ ] Add `apply --json` final envelope.
- [ ] Add `apply --jsonl` event stream.
- [ ] Ensure prompts are CLI-only and API callers pass explicit decisions such as `yes` and `prune_extras`.

### Phase 4: Provisioning Events

- [ ] Add optional reporter to `Provisioner.run()`.
- [ ] Emit `provision.step.started` and `provision.step.completed` from `Provisioner`.
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
