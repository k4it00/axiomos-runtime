# AxiomOS Handshake

**Handover Date:** 2026-07-09  
**Handover Agent:** Hermes Agent (Nous Research)  
**Project:** AxiomOS Runtime 1.1.0-dev0  
**Repository:** [github.com/k4it00/axiomos-runtime](https://github.com/k4it00/axiomos-runtime)

---

## What was built

The build loop began after the user accepted handover and ran:

| Item | Status | Description |
|---|---|---|
| GitHub repo creation | ✅ | `k4it00/axiomos-runtime` (public) |
| Bug fixes | ✅ | Missing imports in `commands.py`, stale version assertions in tests |
| Test verification | ✅ | 39 original tests → all fixed and passing |
| **Executive Function** | ✅ | Decision loop: frame/continue/pivot/ask/abort with memory-aware framing |
| **Goal Shell** | ✅ | Goal lifecycle orchestrator wrapping EF + Hypervisor |
| **CLI wiring** | ✅ | `axiom goal` + `-g` flag + `/goal` shell command |
| **CI pipeline** | ✅ | GitHub Actions: test on push/PR (Python 3.10–3.12) |
| **Nightly cron** | ✅ | Test suite at 04:00 daily, results delivered to this chat |
| **Handoff docs** | ✅ | README, ROADMAP, HANDSHAKE |

**86 tests, all passing.** The test suite runs in <1s.

---

## System state

### Active filesystem

```
/home/k4it0/axiomos_1_1/axiomos_runtime_1_1_dev_self_describing/
├── src/axiomos/
│   ├── cli.py              ← updated: +goal subcommand, -g flag
│   ├── commands.py         ← updated: +/goal dispatch
│   ├── executive_function.py   ← NEW: the metacognitive control loop
│   ├── goal_shell.py       ← NEW: GoalShell lifecycle orchestrator
│   └── ... (existing modules untouched)
├── tests/
│   ├── test_executive_function.py  ← NEW: 37 tests
│   ├── test_goal_shell.py          ← NEW: 10 tests
│   └── ... (39 existing tests untouched)
├── .github/workflows/test.yml  ← NEW: CI
├── README.md          ← updated
├── ROADMAP.md         ← updated
├── HANDSHAKE.md       ← NEW: this file
├── ARCHITECTURE.md    ← exists, describes full architecture
└── CHANGELOG.md
```

### Active git branch

- **Branch:** `master` (pushed to origin)
- **Last commit:** `8a496a6` — "Executive Function + GoalShell + CI: 86 tests, goal lifecycle wiring"
- **Remote:** `origin → https://github.com/k4it00/axiomos-runtime.git`

### Active Hermes Agent cron

- **Job ID:** `c5fb92ba5987`
- **Schedule:** `0 4 * * *` (daily at 04:00)
- **Action:** Runs pytest, reports results to this chat

### Provider config

- **Active provider:** `cf_p26` (Cloudflare Workers AI, model `@cf/meta/llama-3.2-3b-instruct`)
- **Credentials:** In `~/.bashrc` as `CLOUDFLARE_ACCOUNT_ID_P26` / `CLOUDFLARE_API_TOKEN_P26`

### Python environment

- **Venv at:** `.venv/` (under project root)
- **Python:** 3.11.15
- **Package:** axiomos-runtime==1.1.0-dev0 (editable install)

---

## How it works

### Goal lifecycle

```
Goal text
  │
  ▼
ExecutiveFunction.frame_goal(goal)
  │  Analyzes risk/complexity/vagueness
  │  Queries MemoryStore for context
  │  Returns FRAME (with strategy), ASK (vague/risky+no context), or ABORT
  │
  ▼
Hypervisor.run_prompt(framed_goal)
  │  Routes, builds intent, generates receipt
  │  Returns receipt with status + next_steps
  │
  ▼
ExecutiveFunction.review_outcome(verification, history)
  │  Maps receipt → verification status
  │  Checks retry/pivot counts
  │  Returns CONTINUE, PIVOT, ASK, or ABORT
  │
  ▼
GoalShell.submit()
  │  Wraps the full lifecycle
  │  Records decisions to context
  │  Returns final verdict
```

### Decision types

| Action | When | Meaning |
|---|---|---|
| `FRAME` | Pre-execution | Goal framed for hypervisor; ready to execute |
| `CONTINUE` | Post-verification | Step passed → move to next step; or goal complete |
| `PIVOT` | Retries exhausted | Change strategy; try a different approach |
| `ASK` | Vague/no context/all tried | Need human input to proceed |
| `ABORT` | Unknown status | Goal cannot be completed |

### Risk levels

| Risk | Key words | Behavior without context |
|---|---|---|
| `high` | deploy, delete, publish, destroy, pay, transfer | ASK (blocked) |
| `medium` | write, modify, change, update, install | FRAME (proceeds) |
| `low` | (none of the above) | FRAME (proceeds) |

Complexity > 0.7 → strategy = "decompose" instead of "direct".  
Goals < 10 chars or containing vague terms ("do something", "fix it") → ASK.

---

## How to pick up Day 1

1. **Read the docs:**
   - [ARCHITECTURE.md](ARCHITECTURE.md) — full system architecture
   - [ROADMAP.md](ROADMAP.md) — what's next

2. **Run the tests:**
   ```bash
   cd ~/axiomos_1_1/axiomos_runtime_1_1_dev_self_describing
   source .venv/bin/activate
   python -m pytest tests/ -v --tb=line
   ```

3. **Try the goal system:**
   ```bash
   python -m axiomos.cli goal "check python version"
   python -m axiomos.cli goal "list files in current directory"
   python -m axiomos.cli -g "deploy to production"  # should block — no context
   ```

4. **Next milestones (see ROADMAP):**
   - Multi-provider broker (OpenAI, Claude, Ollama)
   - `Goal >` shell prompt replacing `Prompt >`
   - Receipt-driven continuation (multi-step goals)
   - Human-in-the-loop ask/confirm flow

---

## Known limitations

- **`Goal >` shell prompt** is not yet implemented. The interactive shell still shows `Prompt >`. The `/goal` command works within it, and `axiom -g` and `axiom goal` work from the CLI.
- **Multi-step continuation** is wired in the EF review logic (returns next_steps) but GoalShell currently does one pass. A loop in GoalShell is the natural next step.
- **Multi-provider** uses only Cloudflare Workers AI. The provider_config system needs OpenAI/Claude/Ollama backends added.
- **Memory attention** works but compression thresholds are hardcoded in memory.py.
- **Tests are fast** (all 86 in <1s) because API calls use dry-run mode.

---

## Credentials stored in `~/.bashrc`

- `CLOUDFLARE_ACCOUNT_ID_P26`
- `CLOUDFLARE_API_TOKEN_P26`
- `GITHUB_TOKEN` (gh CLI authenticated)

These are sourced by the active shell. AxiomOS reads them from environment via `provider_config.py`.

---

## Final word

This project went from a broken 1.1 zip with 39 mixed tests to a clean, fully-pushed GitHub repo with 86 tests, a working Executive Function, Goal Shell, CI pipeline, and nightlies — in a single automated build loop.

The architecture is sound. The code is tested. The decisions are documented. Pick up from [ROADMAP.md](ROADMAP.md) and ship it.
