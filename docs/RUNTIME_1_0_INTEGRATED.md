# AxiomOS Runtime 1.0 Integrated

## Runtime shape

```text
Transport
  ↓
Hypervisor
  ↓
Policy
  ↓
Capability Broker
  ↓
Scheduler
  ↓
Providers / Tools
  ↓
Verifier
  ↓
Memory OS
  ↓
Receipt
```

## Loop OS

```text
Planner
  ↓
Executor
  ↓
Verifier
  ↓
Reflector
  ↓
Memory
  ↓
Stop / Repair / Retry
```

## Principle

AxiomOS is not a provider wrapper. It is a cognitive runtime where providers and tools are drivers under a permissioned kernel.
