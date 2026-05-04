"""API contract inspection commands."""

from __future__ import annotations

from meridian.console import err_console, error_context, fail, is_json_mode
from meridian.core.models import Summary
from meridian.core.output import OperationContext, envelope
from meridian.core.schema import schema_catalog, schema_for
from meridian.renderers import emit_json


def run_schemas(*, json_output: bool = False, include_schemas: bool = False) -> None:
    """List meridian-core schemas."""
    operation = OperationContext()
    with error_context("api.schemas", timer=operation.timer):
        catalog = schema_catalog(include_schemas=include_schemas and (json_output or is_json_mode()))
    if json_output or is_json_mode():
        emit_json(
            envelope(
                command="api.schemas",
                data={"schemas": catalog},
                summary=Summary(text=f"{len(catalog)} schema(s)", changed=False, counts={"schemas": len(catalog)}),
                timer=operation.timer,
            )
        )
        return

    err_console.print()
    err_console.print("  [bold]Meridian API schemas[/bold]")
    for item in catalog:
        err_console.print(f"    {item['name']}  [dim]{item['title']}[/dim]")
    err_console.print()


def run_schema(name: str, *, envelope_output: bool = False) -> None:
    """Print one meridian-core JSON Schema."""
    operation = OperationContext()
    with error_context("api.schema", timer=operation.timer):
        try:
            schema = schema_for(name)
        except ValueError as exc:
            fail(str(exc), hint="Run: meridian api schemas", hint_type="user")

        if envelope_output or is_json_mode():
            emit_json(
                envelope(
                    command="api.schema",
                    data={"name": name, "schema": schema},
                    summary=Summary(text=f"Schema: {name}", changed=False, counts={"schemas": 1}),
                    timer=operation.timer,
                )
            )
            return

        emit_json(schema)
