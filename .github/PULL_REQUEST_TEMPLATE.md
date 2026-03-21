## Summary
<!-- Brief description of changes -->

## Type of change
- [ ] Bug fix
- [ ] New feature
- [ ] Refactoring
- [ ] Documentation

## Checklist
- [ ] I have read `CONTRIBUTING.md`
- [ ] `make ci` passes locally
- [ ] Updated relevant documentation surfaces (see below)

### If modifying connection info templates:
- [ ] All connection-info templates are in sync (CSS/JS/app links)
- [ ] Tested light and dark mode

### If adding a new CLI command:
- [ ] Added help smoke test in `tests/test_cli.py`
- [ ] Updated README.md commands table
- [ ] Updated CLAUDE.md subcommands list

### If modifying credential handling:
- [ ] Tested with existing credential files (backward compat)
- [ ] Updated `ServerCredentials` dataclass if needed

### If modifying provisioner steps:
- [ ] Step returns proper StepResult (ok/changed/skipped/failed)
- [ ] ProvisionContext fields typed if used by other steps
- [ ] Shell values use shlex.quote()
