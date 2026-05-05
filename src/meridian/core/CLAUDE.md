# core - Meridian API contracts

## Design decisions
- **Core has no CLI globals** - no Typer, Rich, prompt, process exit, or console mode dependencies. CLI and future UI clients are adapters over core contracts.
- **Envelope first** - JSON clients get one stable `meridian.output/v1` result shape; command-specific data lives under `data`.
- **Events are JSONL-ready** - long-running flows should report progress as typed events, not ad hoc log lines.
- **Pydantic at API boundaries** - public request/result/event/error contracts use Pydantic v2 for validation, JSON serialization, and JSON Schema export. Internal execution objects can stay lighter until they cross a client boundary.
- **Exported services return typed contracts** - service result wrappers are Pydantic too; do not publish dataclasses as core API.

## What's done well
- Shared serializers keep JSON output stable and recursively handle core Pydantic models.
- Redaction is centralized so expanding JSON/API surfaces does not multiply secret-leak risk.
- Fleet inventory is built as a redacted result object before any CLI rendering happens.
- Client list/show use the same service/result/envelope pattern as fleet reads.

## Pitfalls
- Do not import command modules, `meridian.console`, Typer, or Rich here.
- Do not emit raw SSH commands, panel tokens, private keys, JWTs, database URLs, or subscription secrets.
- Keep human wording in adapters; core summaries are short API metadata, not terminal copy.
- Generated JSON Schemas are public data; redaction must preserve `properties` definitions while still redacting real secret values.
