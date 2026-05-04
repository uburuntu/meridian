# TODO

## Platformization Goal

Meridian should become a structured installation and control API with a CLI client on top. Human terminal output stays polished, but the core product contract should be typed requests, typed results, structured errors, and structured progress events.

The guiding rule: command modules parse CLI arguments and choose renderers; they should not own business logic, JSON schema, prompts inside core flows, or process exits below the entrypoint.

## Product Assumptions

- Text output remains the default UX.
- `--json` means one final machine-readable result on stdout.
- `--jsonl` means machine-readable event stream on stdout for long-running operations.
- Human logs/progress go to stderr or are suppressed in API modes.
- JSON/API modes are non-interactive by default. Missing input returns a structured user error.
- Secrets are never emitted in JSON, JSONL, errors, event data, command metadata, or logs.
- Current process exit codes stay compatible for now; JSON `status` and `error.category` carry richer meaning.

## Product Questions

- [ ] Is the first-class API contract only the CLI process contract, or should Meridian also expose a supported Python API?
- [ ] Should `--json` immediately use the new envelope everywhere, or should legacy payloads be wrapped under `result` for one major version?
- [ ] Should `--json` imply `--no-input` everywhere, or should any command be allowed to request input through JSONL events?
- [ ] Do automation users need live progress on stdout via `--jsonl`, or is final JSON plus stderr progress enough for v1?
- [ ] Is `plan` exit code `2` for changes-pending sacred, even though `2` also means user errors elsewhere?
- [ ] Which commands are contract-stable in v1, and which stay best-effort/internal until later?
- [ ] Should API fields optimize for shell/JQ consumers, Python SDK consumers, or both equally?

## Target Architecture

- [ ] `meridian.api`: product use cases and request/result models; no Typer, Rich, `print`, or `typer.Exit`.
- [ ] `meridian.api.models`: stable dataclasses for envelopes, errors, events, plans, inventory, clients, nodes, relays, deployment results, and provision results.
- [ ] `meridian.api.services`: service functions such as `get_fleet_inventory()`, `compute_apply_plan()`, `apply_desired_state()`, `deploy_node()`, `deploy_relay()`, `add_client()`.
- [ ] `meridian.api.renderers`: JSON, JSONL, and Rich/text renderers over the same result/event objects.
- [ ] `meridian.api.reporters`: event sink abstraction for provisioners, reconciler execution, SSH diagnostics, warnings, and prompts.
- [ ] `meridian.cli`: Typer argument parsing, request construction, renderer selection, prompt collection, and exit-code mapping only.
- [ ] Keep adapters explicit: Remnawave API, SSH, filesystem cluster store, cloud providers, and template rendering.

## JSON Envelope v1

- [ ] Define `meridian.output/v1` for every non-streaming JSON result.
- [ ] Standardize top-level fields:
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
- [ ] Use `status` values: `ok`, `changed`, `no_changes`, `failed`, `cancelled`.
- [ ] Make `data` command-specific and stable by command.
- [ ] Make `summary` structured enough for dashboards, not only prose.
- [ ] Use one shared warning/error object shape in both `warnings` and `errors`.
- [ ] Add serializer unit tests for envelope success, warning, failure, and redaction cases.
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

- [ ] Define `MeridianError` with:
  - `code`
  - `category`
  - `message`
  - `hint`
  - `retryable`
  - `exit_code`
  - `details`
  - `cause`
- [ ] Use categories: `user`, `system`, `bug`, `cancelled`.
- [ ] Replace deep `console.fail()` calls with structured exceptions/results below CLI entrypoints.
- [ ] Keep CLI entrypoints responsible for rendering human errors and mapping to `typer.Exit`.
- [ ] Add JSON-mode error tests for user, system, bug, and cancelled paths.
- [ ] Add redaction tests for panel tokens, admin passwords, private keys, JWT secrets, database URLs, API tokens, and subscription secrets.

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

- [ ] Define `meridian.event/v1` for streaming progress.
- [ ] Standardize fields:
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
- [ ] Guarantee monotonic `seq` for global ordering, including parallel apply.
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

- [ ] Add `meridian.api.models` with output envelope, event, summary, and error dataclasses.
- [ ] Add JSON and JSONL serializer helpers with stable key ordering.
- [ ] Add `operation_id` generation and monotonic event sequence support.
- [ ] Add redaction utilities shared by SSH, JSON, JSONL, and diagnostics.
- [ ] Add golden contract tests for envelope and error rendering.

### Phase 2: Read-Only Commands First

- [ ] Move `fleet inventory` result construction into a service returning a typed result.
- [ ] Render `fleet inventory` text and JSON from that typed result.
- [ ] Move `fleet status` result construction into a service returning a typed result.
- [ ] Render `fleet status` text and JSON from that typed result.
- [ ] Move `client list` and `client show` to service/result/renderer boundaries.
- [ ] Preserve existing human output while adding envelope JSON.

### Phase 3: Plan and Apply

- [ ] Convert `plan --json` to the shared envelope while preserving legacy shape under `data` or a compatibility key.
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
- [ ] Changing `plan --json` may break current scripts unless the compatibility path is explicit.
- [ ] Rich progress must remain polished when moved behind event renderers.

## Near-Term First Slice

- [ ] Build `meridian.api.models` with `OutputEnvelope`, `MeridianError`, and `Event`.
- [ ] Build shared `emit_json()` and `emit_jsonl()` renderers.
- [ ] Add command-local `--json` support to all read-only commands.
- [ ] Migrate `fleet inventory` to service/result/renderers.
- [ ] Migrate `plan` to shared envelope and add compatibility tests.
- [ ] Add JSON error rendering at CLI entrypoint boundary.
- [ ] Add redaction tests before expanding JSON surface area further.
