# AxiomOS Runtime 1.1.0-dev0

**Universal cognitive operating system.** From goal framing to execution verification — AxiomOS is a model-agnostic agent runtime with memory, tools, capability routing, package system, and an executive function decision loop.

[![CI](https://github.com/k4it00/axiomos-runtime/actions/workflows/test.yml/badge.svg)](https://github.com/k4it00/axiomos-runtime/actions/workflows/test.yml)

---

## Quick start

```bash
pip install -e .

# Submit a goal through the Executive Function lifecycle
axiom -g "check python version"
axiom goal "list files in current directory"

# CLI shell
axiom

# CLI shell commands
/help
/about
/providers list
/memory stats
/memory search "python"
/goal my goal text
```

## Architecture

```
Memory ──► Executive Function ──► Policy Gate ──► Hypervisor ──► Execution
                ▲                                    │
                └────────── Verifier ◄────────────────┘

Cross-cutting: Receipts, Tools, Capability Broker, Provider Config
```

- **Executive Function** — decision loop: frame → execute → verify → review → continue/pivot/ask/abort
- **Goal Shell** — wraps EF + Hypervisor into a `Goal >` lifecycle
- **Memory** — semantic index with attention, conflict detection, compression
- **Hypervisor** — prompt routing, dry-run/execute, receipt generation
- **Capability Broker** — routes intents to package capabilities
- **Tool Registry** — register and sandbox tools (filesystem, executable)
- **Package System** — install/show/doctor manifest-driven packages
- **Receipts** — structured audit trail for every operation

## Commands

### Goal (new in 1.1)

```bash
axiom goal "your goal text here"
axiom -g "your goal text here"
```

The goal lifecycle:
1. **Frame** — EF analyzes risk/complexity/vagueness, consults memory
2. **Route** — Hypervisor routes the framed goal
3. **Execute** — dry-run (default) or real execution with `--execute`
4. **Verify** — receipt verification
5. **Review** — EF decides: continue, pivot, ask human, or abort

Vague/risky goals without memory context are **blocked** with an explanation.

### Setup & Config

```bash
axiom setup --dry-run
axiom setup provider cloudflare cf_p26 --account-env CF_ACCOUNT --token-env CF_TOKEN
axiom setup memory --attention-limit 7
axiom setup permissions --profile dev

axiom config init
axiom config list
axiom config get provider.default
axiom config set provider.default cf_p26
```

### Self-description

```bash
axiom about              # full payload
axiom about status       # project status
axiom about roadmap      # roadmap
axiom about architecture # architecture doc
axiom about constitution # constitution
```

## Home Layout

```
~/.axiom/
  config.yaml
  .env
  identity/
  memory/
  packages/
  receipts/
  skills/
  cron/
```

Secrets go to `.env`. Non-secret settings go to `config.yaml`.

## Testing

```bash
python -m pytest tests/ -v --tb=line
```

**86 tests** covering:
- 39 original (setup/config, broker, memory, tools, packages, pipeline, receipts)
- 37 Executive Function (framing, review, context, config, edge cases)
- 10 Goal Shell (submission, blocking, multiple goals, serialization)

## Requirements

- Python 3.10–3.12
- Cloudflare Workers AI token (for AI inference)
- Linux (tested on Ubuntu 24.04)

## Project Status

- **Version:** 1.1.0-dev0
- **Tests:** 86/86 passing
- **CI:** GitHub Actions (push + PR, Python 3.10/3.11/3.12)
- **Nightly cron:** test suite at 04:00 daily via Hermes Agent
- **Goal lifecycle:** Executive Function fully implemented and wired
- **Next:** see [ROADMAP.md](ROADMAP.md)

## Handover

This project was handed over by the original author to Hermes Agent on 2026-07-09 for completion. The build loop built: EF module, Goal Shell, CLI wiring, CI, and this documentation. See [HANDSHAKE.md](HANDSHAKE.md) for the full handoff context.
