# tests/provision — Provisioner step tests

## Mock boundary

**Mocked**: `ServerConnection.run()` via `MockConnection` (substring-pattern matching).
**Not mocked**: step logic, `StepResult`, credential generation.

We test the step's *decision logic* — not the shell commands it runs.

## Idempotency testing pattern

Every step test has two paths:
- **Already done** — mock returns "installed" → step returns `status="ok"`, no install called
- **Needs change** — mock returns partial state → step returns `status="changed"`, install called

This catches regressions where a step stops checking state before acting.

## Pitfalls

- **Mock rule order** — first matching pattern wins. Register more specific patterns first.
- **`ProvisionContext` dict keys** — steps read from `ctx["key"]`. Missing key = `KeyError` at runtime, not test time. Pipeline contract tests (`test_contract.py`) catch these.
