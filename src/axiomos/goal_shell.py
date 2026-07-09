"""
GoalShell — AxiomOS goal-driven interface.

Wraps Executive Function + Hypervisor into a goal lifecycle:
  Frame → Execute → Verify → Review → Decide → (continue|pivot|ask|abort|deliver)

Called from the Shell, from `-q` one-shot, and from /goal commands.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import json

from .executive_function import (
    ExecutiveFunction, ExecutiveDecision, ExecutiveAction, GoalContext,
)
from .hypervisor import run_prompt
from .memory import MemoryStore
from .receipts import make_receipt, show_receipt
from .config import load_config


class GoalShell:
    """
    Goal lifecycle orchestrator.

    Takes a user goal and runs it through the full EF → Hypervisor → Verify → Review loop.
    Returns a structured result with the decision, receipt, and next actions.

    Future: parallel sub-goal execution, LLM-assisted decomposition,
           recovery from interrupted goal contexts.
    """

    def __init__(self, workspace: str = ".", memory: MemoryStore | None = None, config: dict | None = None):
        self.workspace = Path(workspace)
        self.config = config or load_config()
        self.memory = memory
        self.ef = ExecutiveFunction(
            workspace=workspace,
            config=self.config,
            memory_store=memory,
        )
        self._active_goals: dict[str, GoalContext] = {}

    # ── Public API ─────────────────────────────────────────────────────────

    def submit(self, goal: str, execute: bool = False) -> dict[str, Any]:
        """
        Submit a goal for processing.

        Full lifecycle:
          1. EF.frame_goal() → decision + frame
          2. If ASK → return immediately asking for clarification
          3. hypervisor.run_prompt() → receipt
          4. Extract verification info from receipt
          5. EF.review_outcome() → continue/pivot/ask/abort
          6. Return structured result

        Returns a dict with:
          - status: str
          - decision: ExecutiveDecision (as dict)
          - receipt: dict | None
          - goal_context: dict
          - human_prompt: str | None (if ASK)
        """
        # ── 1. Create goal context ──
        ctx = self.ef.create_context(goal)
        self._active_goals[ctx.goal_id] = ctx

        # ── 2. Frame the goal ──
        frame_decision = self.ef.frame_goal(goal)
        self.ef.record_decision(ctx, frame_decision)

        # If EF says ASK, return immediately
        if frame_decision.action == ExecutiveAction.ASK:
            return {
                "status": "blocked",
                "decision": frame_decision.to_dict(),
                "receipt": None,
                "goal_context": ctx.to_dict(),
                "human_prompt": frame_decision.reasoning[0] if frame_decision.reasoning else "Goal needs clarification",
            }

        # ── 3. Execute via hypervisor ──
        prompt = self._build_prompt_from_frame(frame_decision)
        receipt = run_prompt(prompt, dry_run=not execute, workspace=str(self.workspace))
        receipt_dict = receipt if isinstance(receipt, dict) else {"raw": str(receipt)}

        # ── 4. Build verification status ──
        verification = self._extract_verification(receipt_dict)

        # ── 5. Review outcome ──
        review_decision = self.ef.review_outcome(goal, verification)
        self.ef.record_decision(ctx, review_decision)

        result = {
            "status": review_decision.action.value,
            "decision": review_decision.to_dict(),
            "receipt": receipt_dict,
            "goal_context": ctx.to_dict(),
            "human_prompt": None,
        }

        if review_decision.action == ExecutiveAction.ASK:
            result["human_prompt"] = review_decision.reasoning[0] if review_decision.reasoning else "Need human input"
            result["status"] = "blocked"

        if review_decision.action == ExecutiveAction.CONTINUE and review_decision.frame.get("status") == "complete":
            result["status"] = "completed"

        return result

    def status(self, goal_id: str | None = None) -> list[dict]:
        """List active goal contexts."""
        if goal_id:
            ctx = self._active_goals.get(goal_id)
            return [ctx.to_dict()] if ctx else []
        return [ctx.to_dict() for ctx in self._active_goals.values()]

    def active_count(self) -> int:
        return len(self._active_goals)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _build_prompt_from_frame(self, decision: ExecutiveDecision) -> str:
        """Build a hypervisor-ready prompt from an EF frame decision."""
        frame = decision.frame
        strategy = frame.get("strategy", "direct")

        if strategy == "decompose":
            sub_goals = frame.get("sub_goals", [decision.goal])
            return (
                f"Goal: {decision.goal}\n"
                f"This is a complex multi-step goal decomposed into sub-goals:\n"
                + "\n".join(f"  {i+1}. {sg}" for i, sg in enumerate(sub_goals))
                + "\n\nExecute each sub-goal and report results."
            )

        context = frame.get("memory_attention", [])
        context_block = ""
        if context:
            context_block = "\nRelevant memory context:\n" + "\n".join(
                f"  - {c[:150]}" for c in context
            )

        return (
            f"Goal: {decision.goal}\n"
            f"Risk: {frame.get('risk', 'unknown')}\n"
            f"Complexity: {frame.get('complexity', 0.5):.2f}"
            f"{context_block}"
        )

    def _extract_verification(self, receipt: dict) -> dict[str, Any]:
        """Extract verification status from an execution receipt."""
        status = receipt.get("status", "unknown")
        reason = receipt.get("reason") or receipt.get("error") or "No details"

        # Map various receipt statuses to EF verification conventions
        if status in ("passed", "success", "ok", "done"):
            return {"status": "passed"}
        if status in ("failed", "error", "blocked"):
            return {"status": "failed", "reason": reason}
        if status in ("dry-run", "simulated", "dry_run_planned"):
            return {"status": "passed", "next_steps": receipt.get("next_steps", [])}
        if status == "executed":
            return {"status": "passed", "next_steps": receipt.get("next_steps", [])}

        return {"status": "passed" if receipt.get("success") else "unknown", "reason": reason}
