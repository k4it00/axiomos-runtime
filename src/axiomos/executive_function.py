from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal
import json, uuid


# ─── Decision Types ───────────────────────────────────────────────────────────

class ExecutiveAction(Enum):
    """The possible decisions Executive Function can return."""
    FRAME = "frame"         # Initial goal framing → hypervisor
    CONTINUE = "continue"   # Keep going with next step
    PIVOT = "pivot"         # Change strategy
    ASK = "ask"             # Need human input
    ABORT = "abort"         # Goal not achievable


@dataclass
class ExecutiveDecision:
    """
    A single decision from Executive Function.

    At the FRAME stage: tells the hypervisor how to approach the goal.
    At the REVIEW stage: tells the caller what to do next.
    """
    action: ExecutiveAction
    goal: str
    frame: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    reasoning: list[str] = field(default_factory=list)
    requires_human: bool = False
    next_actions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action"] = self.action.value
        return d


@dataclass
class GoalContext:
    """
    Tracks the lifecycle of a single goal through EF ↔ hypervisor ↔ verifier.
    Persisted to memory for audit and recovery.
    """
    goal_id: str
    goal: str
    status: Literal["framing", "executing", "verifying", "completed", "aborted", "blocked"]
    decisions: list[ExecutiveDecision] = field(default_factory=list)
    attempt_count: int = 0
    pivot_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "goal": self.goal,
            "status": self.status,
            "decisions": [d.to_dict() for d in self.decisions],
            "attempt_count": self.attempt_count,
            "pivot_count": self.pivot_count,
            "created_at": self.created_at,
        }


# ─── Executive Function ───────────────────────────────────────────────────────

class ExecutiveFunction:
    """
    The cognitive control loop for AxiomOS.

    Decides what to do with a goal at three points:

    1. FRAME — How to frame it for the Hypervisor.
       - Direct: simple goal, single pass
       - Decompose: complex goal, needs sub-steps
       - Ask: ambiguous, needs human clarification

    2. REVIEW — After verification, what next?
       - Continue: step succeeded → next step or done
       - Retry: recoverable failure, try again
       - Pivot: strategy failing, change approach
       - Ask: all strategies exhausted

    3. RECOVERY — On hard failure / crash, restore from persisted context.

    Thresholds are read from config (or sensible defaults) so the system
    can tune its own risk appetite over time.
    """

    def __init__(self, workspace: str = ".", config: dict[str, Any] | None = None, memory_store=None):
        self.workspace = Path(workspace)
        self.config = config or {}
        self.memory = memory_store

        # Decision thresholds — overridable via config
        ef_cfg = config.get("executive", {}) if config else {}
        self.max_retries = int(ef_cfg.get("max_retries", 3))
        self.max_pivots = int(ef_cfg.get("max_pivots", 2))
        self.conf_continue = float(ef_cfg.get("confidence_continue", 0.6))
        self.conf_pivot = float(ef_cfg.get("confidence_pivot", 0.3))
        self.conf_ask = float(ef_cfg.get("confidence_ask", 0.15))

        # Active goal tracker
        self._active: dict[str, GoalContext] = {}

    # ── Public API ─────────────────────────────────────────────────────────

    def frame_goal(self, goal: str, context: dict | None = None) -> ExecutiveDecision:
        """
        PRE-EXECUTION: Given a raw goal, decide how to frame it.

        Returns a decision + frame dict the Hypervisor uses to plan execution.
        """
        # Gather memory context if available
        context_records = []
        if self.memory:
            attention = self.memory.attention(goal, limit=5)
            context_records = attention.get("selected", [])

        complexity = self._estimate_complexity(goal)
        risk = self._assess_risk(goal)
        is_vague = self._is_vague(goal)

        # Build the frame
        frame = {
            "goal": goal,
            "strategy": "direct",
            "complexity": complexity,
            "risk": risk,
            "context_records": len(context_records),
            "memory_attention": [r.get("content", "")[:200] for r in context_records],
        }

        # ── Decision tree ──
        if is_vague:
            return ExecutiveDecision(
                action=ExecutiveAction.ASK,
                goal=goal,
                frame=frame,
                confidence=0.2,
                reasoning=["Goal is too vague or too short for confident execution"],
                requires_human=True,
            )

        if risk == "high" and not context_records:
            return ExecutiveDecision(
                action=ExecutiveAction.ASK,
                goal=goal,
                frame={**frame, "strategy": "ask"},
                confidence=0.35,
                reasoning=[
                    "High-risk goal with no relevant memory context",
                    "Cannot proceed without human confirmation",
                ],
                requires_human=True,
            )

        if complexity > 0.65:
            # Complex → decompose into sub-goals
            sub_goals = self._decompose(goal, risk)
            frame["strategy"] = "decompose"
            frame["sub_goals"] = sub_goals
            return ExecutiveDecision(
                action=ExecutiveAction.FRAME,
                goal=goal,
                frame=frame,
                confidence=0.7,
                reasoning=[
                    f"Complex goal (score: {complexity:.2f})",
                    f"Decomposed into {len(sub_goals)} sub-goals",
                    f"Risk level: {risk}",
                ],
                next_actions=sub_goals,
            )

        return ExecutiveDecision(
            action=ExecutiveAction.FRAME,
            goal=goal,
            frame=frame,
            confidence=0.85,
            reasoning=[
                f"Simple goal (score: {complexity:.2f})",
                "Direct execution strategy",
            ],
        )

    def review_outcome(
        self,
        goal: str,
        verification: dict[str, Any],
        history: list[dict[str, Any]] | None = None,
    ) -> ExecutiveDecision:
        """
        POST-VERIFICATION: Given verification results, decide what to do next.

        Uses retry/pivot budgets from config to avoid infinite loops.
        """
        history = history or []
        v_status = verification.get("status", "unknown")

        if v_status == "passed":
            next_steps = verification.get("next_steps", [])
            if next_steps:
                return ExecutiveDecision(
                    action=ExecutiveAction.CONTINUE,
                    goal=goal,
                    frame={"next_step": next_steps[0]},
                    confidence=0.9,
                    reasoning=["Step completed", f"Next: {next_steps[0]}"],
                    next_actions=next_steps,
                )
            return ExecutiveDecision(
                action=ExecutiveAction.CONTINUE,
                goal=goal,
                frame={"status": "complete"},
                confidence=0.95,
                reasoning=["Goal completed successfully"],
            )

        if v_status in ("failed", "blocked", "error"):
            failures = [h for h in history if h.get("status") in ("failed", "blocked", "error")]
            retry_count = len(failures) + 1  # +1 for this failure

            if retry_count < self.max_retries:
                return ExecutiveDecision(
                    action=ExecutiveAction.CONTINUE,
                    goal=goal,
                    frame={"strategy": "retry", "retry_count": retry_count},
                    confidence=max(0.3, self.conf_continue - retry_count * 0.1),
                    reasoning=[
                        f"Execution failed ({retry_count}/{self.max_retries})",
                        verification.get("reason", "Unknown failure"),
                        "Retrying with same strategy",
                    ],
                )

            pivots = len([h for h in history if h.get("pivot")])
            if pivots < self.max_pivots:
                return ExecutiveDecision(
                    action=ExecutiveAction.PIVOT,
                    goal=goal,
                    frame={"strategy": "pivot", "pivot_count": pivots + 1},
                    confidence=self.conf_pivot,
                    reasoning=[
                        f"Retries exhausted ({self.max_retries})",
                        f"Pivoting strategy ({pivots + 1}/{self.max_pivots})",
                    ],
                )

            return ExecutiveDecision(
                action=ExecutiveAction.ASK,
                goal=goal,
                frame={"status": "blocked_after_all_strategies"},
                confidence=self.conf_ask,
                reasoning=[
                    "All retries and pivots exhausted",
                    "Need human guidance to proceed",
                ],
                requires_human=True,
            )

        if v_status == "verification_pending":
            return ExecutiveDecision(
                action=ExecutiveAction.ASK,
                goal=goal,
                frame={"status": "pending_external_verification"},
                confidence=0.5,
                reasoning=["Result requires external human verification"],
                requires_human=True,
            )

        return ExecutiveDecision(
            action=ExecutiveAction.ABORT,
            goal=goal,
            frame={"status": "aborted", "reason": f"unknown_verification_status: {v_status}"},
            confidence=0.3,
            reasoning=[f"Cannot interpret verification status: {v_status}"],
        )

    def create_context(self, goal: str) -> GoalContext:
        """Create and track a new goal context."""
        ctx = GoalContext(goal_id="g_" + uuid.uuid4().hex[:10], goal=goal, status="framing")
        self._active[ctx.goal_id] = ctx
        return ctx

    def record_decision(self, ctx: GoalContext, decision: ExecutiveDecision):
        """Record a decision against a goal context."""
        ctx.decisions.append(decision)
        if decision.action == ExecutiveAction.FRAME:
            ctx.status = "executing"
            ctx.attempt_count += 1
        elif decision.action in (ExecutiveAction.ABORT, ExecutiveAction.ASK):
            ctx.status = "blocked" if decision.requires_human else "aborted"
        elif decision.action == ExecutiveAction.PIVOT:
            ctx.pivot_count += 1
        if ctx.status == "executing" and self.memory:
            self.memory.append(
                "episodic",
                f"Executive Decision: {decision.action.value} — {decision.reasoning[0] if decision.reasoning else ''}",
                tags=("executive", decision.action.value, ctx.goal_id),
                metadata={"goal_id": ctx.goal_id, "decision": decision.to_dict()},
            )

    # ── Internal heuristics ────────────────────────────────────────────────

    def _estimate_complexity(self, goal: str) -> float:
        """Estimate goal complexity on [0, 1]."""
        g = goal.lower()
        words = g.split()
        sentence_count = max(g.count(".") + g.count("!") + g.count("?"), 1)
        word_count = len(words)

        # Heuristics
        has_substeps = any(kw in g for kw in ["then", "after that", "next", "also", "and then"])
        has_conditions = any(kw in g for kw in ["if", "when", "unless", "except", "but"])
        has_multiple_verbs = sum(1 for v in ["fix", "build", "create", "write", "update",
                                              "deploy", "test", "review", "analyze", "check"]
                                 if v in g) > 1

        score = 0.2
        score += min(word_count / 60, 0.3)           # Length
        score += min(sentence_count * 0.08, 0.2)      # Multi-sentence
        if has_substeps: score += 0.15
        if has_conditions: score += 0.1
        if has_multiple_verbs: score += 0.2

        return min(score, 1.0)

    def _assess_risk(self, goal: str) -> Literal["low", "medium", "high"]:
        """Goal-level risk assessment via keyword matching."""
        g = goal.lower()
        high = {"deploy", "publish", "release", "delete", "destroy", "pay", "transfer", "push"}
        medium = {"write", "modify", "change", "update", "create", "install", "exec",
                  "run", "execute", "commit", "merge", "build"}
        high_match = len(high & set(g.split()))
        medium_match = len(medium & set(g.split()))
        if high_match: return "high"
        if medium_match: return "medium"
        return "low"

    def _is_vague(self, goal: str) -> bool:
        """Detect goals too vague for confident execution."""
        g = goal.lower().strip()
        if len(g) < 12:
            return True
        vague = {"something", "things", "stuff", "fix it", "make it work",
                 "do something", "help me", "i need", "can you"}
        return any(v in g for v in vague)

    def _decompose(self, goal: str, risk: str) -> list[str]:
        """
        Break a complex goal into constituent sub-goals.
        Rule-based decomposition — LLM-assisted decomposition is a future feature.
        """
        g = goal.lower()
        sub_goals = []

        # Detect multi-domain patterns
        if "and" in g or "then" in g:
            # Split on known connectors
            parts = goal.replace(" and then ", "|||").replace(" then ", "|||").replace(" and also ", "|||")
            for part in parts.split("|||"):
                stripped = part.strip().strip(".,")
                if stripped and len(stripped) > 10:
                    sub_goals.append(stripped)

        if not sub_goals:
            # No natural decomposition found, return as single goal
            sub_goals.append(goal)

        return sub_goals[:4]  # Max 4 sub-goals
