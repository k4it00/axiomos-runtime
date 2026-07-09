# AxiomOS Runtime 1.0 Final Release Notes

## Status

Final release built from RC1 after audit verification.

## Final hardening since RC1

- Version bumped to `1.0.0`
- Added `axiom compile FILE` alias for `.ax` → plan output
- Added `--progress` support for long `--execute` calls
- Added provider failover test coverage
- Added cleaner CLI descriptions for final commands
- Cleaned release ZIP: no `.axiom`, `axiom_runs`, `tmp_*`, `.pytest_cache`, or stale alpha READMEs

## Core capabilities

- Parser/validator/IR/graph/plan
- Provider pool and broker
- Identity injection
- Memory OS
- Package system
- Tool drivers
- Permission kernel
- Loop OS
- Receipts
- Doctor

## Not included in 1.0

- Browser automation driver
- Telegram transport
- MCP driver
- GUI/Web app
- Autonomous continuous self-hosting mode

These are post-1.0 features.
