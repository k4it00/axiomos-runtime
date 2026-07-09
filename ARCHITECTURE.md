# AxiomOS Architecture

```text
Goal
  │
  ▼
Executive Function ◄──── Memory (attention context)
  │                    ◄──── Verifier (retry/pivot/abort signal)
  │ ───► Human (ask for input)
  │
  ▼
Hypervisor ◄──── Memory (attention context)
  │
  ├── Policy (boundary gates)
  ├── Capability Broker ──► Provider Pool (GPT, Claude, Ollama, ...)
  └── Tool Registry ──► Driver execution (filesystem, git, shell)
          │
          ▼
       Result
          │
     ┌────┼────┐
     │    │    │
  Verifier Memory Receipts
     │    │    (emitted at every stage)
     │    │
     └────┘
          │
  Executive Function Review
    ── Continue ──► Goal (next step)
    ── Pivot ─────► Goal (re-frame)
    ── Ask ───────► Human
    ── Abort ─────► Done
    ── Complete ──► Done + Final Receipt
```

Models and tools are sibling drivers under the Hypervisor.
