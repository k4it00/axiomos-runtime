# LOOPS.md

## Android Mic Regression Loop

### Goal

Find the smallest verified fix for Android microphone regression.

### Action

Inspect permission flow, WebView/native bridge assumptions, and voice state machine.

### Acceptance Check

Real-device or emulator smoke test confirms mic permission prompt and transcript capture.

### Stop Condition

Stop after 2 passes.

### Approval Boundaries

- Do not modify signing credentials.
