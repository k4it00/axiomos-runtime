"""
Tests for Executive Function — the cognitive control loop.
"""
from __future__ import annotations
import json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from axiomos.executive_function import (
    ExecutiveFunction,
    ExecutiveDecision,
    ExecutiveAction,
    GoalContext,
)


# ─── HELPERS ───────────────────────────────────────────────────────────────────

class FakeMemory:
    """A minimal memory stub that returns canned attention results."""
    def __init__(self, records=None):
        self.records = records or []
        self.appended = []

    def attention(self, query, limit=5):
        return {"selected": self.records[:limit]}

    def append(self, store_type, content, tags=(), metadata=None):
        self.appended.append((store_type, content, tags, metadata))


def simple_decision(d: ExecutiveDecision) -> dict:
    """Convert a decision to a minimal dict for assertion."""
    return {"action": d.action.value, "confidence": round(d.confidence, 2), "requires_human": d.requires_human}


# ─── FRAME TESTS ──────────────────────────────────────────────────────────────

class TestFrameGoal:
    def test_simple_goal(self):
        ef = ExecutiveFunction(config={})
        d = ef.frame_goal("Update the README with the new API endpoints")
        assert d.action == ExecutiveAction.FRAME
        assert d.confidence >= 0.8
        assert not d.requires_human
        assert d.frame["strategy"] == "direct"

    def test_vague_goal_triggers_ask(self):
        ef = ExecutiveFunction(config={})
        d = ef.frame_goal("do something")
        assert d.action == ExecutiveAction.ASK
        assert d.requires_human
        assert d.confidence < 0.3

    def test_very_short_goal(self):
        ef = ExecutiveFunction(config={})
        d = ef.frame_goal("hi")
        assert d.action == ExecutiveAction.ASK

    def test_complex_goal_decomposes(self):
        ef = ExecutiveFunction(config={})
        goal = "Create a new authentication system then write tests for it"
        d = ef.frame_goal(goal)
        assert d.action == ExecutiveAction.FRAME
        assert d.frame["strategy"] == "decompose"
        assert len(d.frame.get("sub_goals", [])) >= 2
        assert len(d.next_actions) >= 2

    def test_high_risk_complex_goals_to_deploy_asks_without_context(self):
        ef = ExecutiveFunction(config={})
        goal = "Create a new authentication system then write tests for it then deploy to staging"
        d = ef.frame_goal(goal)
        # Deploy is high-risk and there's no memory context — must ask
        assert d.action == ExecutiveAction.ASK
        assert d.requires_human

    def test_high_risk_no_context_asks(self):
        ef = ExecutiveFunction(config={}, memory_store=FakeMemory(records=[]))
        d = ef.frame_goal("Deploy the application to production")
        assert d.action == ExecutiveAction.ASK
        assert d.requires_human

    def test_high_risk_with_context_proceeds(self):
        ef = ExecutiveFunction(config={}, memory_store=FakeMemory(records=[
            {"content": "Previous deployment: success with rollback plan",
             "type": "episodic", "id": "rec1"},
        ]))
        d = ef.frame_goal("Deploy the application to production")
        # With memory context, high-risk should proceed with caution
        assert d.action in (ExecutiveAction.FRAME, ExecutiveAction.ASK)
        if d.action == ExecutiveAction.FRAME:
            assert d.frame["strategy"] in ("direct", "decompose")
            assert d.confidence >= 0.5  # Memory-context-informed confidence

    def test_medium_risk_proceeds(self):
        ef = ExecutiveFunction(config={})
        d = ef.frame_goal("Write a new endpoint for user profiles")
        assert d.action == ExecutiveAction.FRAME
        assert not d.requires_human

    def test_risk_assessment_high(self):
        ef = ExecutiveFunction(config={})
        assert ef._assess_risk("Deploy to production") == "high"
        assert ef._assess_risk("Publish the package") == "high"
        assert ef._assess_risk("Delete old files") == "high"

    def test_risk_assessment_medium(self):
        ef = ExecutiveFunction(config={})
        assert ef._assess_risk("Write documentation") == "medium"
        assert ef._assess_risk("Update configuration") == "medium"
        assert ef._assess_risk("Create new module") == "medium"

    def test_risk_assessment_low(self):
        ef = ExecutiveFunction(config={})
        assert ef._assess_risk("Review the log files") == "low"
        assert ef._assess_risk("List all projects") == "low"

    def test_complexity_scores(self):
        ef = ExecutiveFunction(config={})
        assert ef._estimate_complexity("hi") < 0.4
        assert ef._estimate_complexity("Write a simple test") < 0.6
        c = ef._estimate_complexity(
            "Create a new user auth system then deploy it, "
            "if tests pass then merge to main, and finally "
            "write documentation for the new feature"
        )
        assert c > 0.6

    def test_vague_detection(self):
        ef = ExecutiveFunction(config={})
        assert ef._is_vague("fix it")
        assert ef._is_vague("do something")
        assert ef._is_vague("can you help me")
        assert not ef._is_vague("Update the README with API endpoints")


# ─── REVIEW TESTS ─────────────────────────────────────────────────────────────

class TestReviewOutcome:
    def test_verification_passed_no_next_steps(self):
        ef = ExecutiveFunction(config={})
        d = ef.review_outcome("Fix bug in parser", {"status": "passed"})
        assert d.action == ExecutiveAction.CONTINUE
        assert d.frame.get("status") == "complete"
        assert d.confidence > 0.9

    def test_verification_passed_with_next_steps(self):
        ef = ExecutiveFunction(config={})
        d = ef.review_outcome("Build auth system", {
            "status": "passed",
            "next_steps": ["Write integration tests", "Deploy to staging"],
        })
        assert d.action == ExecutiveAction.CONTINUE
        assert d.frame.get("next_step") == "Write integration tests"
        assert len(d.next_actions) == 2

    def test_verification_failed_retries(self):
        ef = ExecutiveFunction(config={"executive": {"max_retries": 3}})
        d = ef.review_outcome("Fix flaky test", {
            "status": "failed",
            "reason": "Timeout error",
        })
        assert d.action == ExecutiveAction.CONTINUE
        assert d.frame.get("strategy") == "retry"
        assert d.confidence < 0.6  # Reduced confidence after failure

    def test_retry_exhausted_triggers_pivot(self):
        ef = ExecutiveFunction(config={"executive": {"max_retries": 2, "max_pivots": 2}})
        history = [
            {"status": "failed", "reason": "Attempt 1"},
            {"status": "failed", "reason": "Attempt 2"},
        ]
        d = ef.review_outcome("Fix complex bug", {
            "status": "failed",
            "reason": "Attempt 3",
        }, history=history)
        assert d.action == ExecutiveAction.PIVOT
        assert d.frame.get("strategy") == "pivot"

    def test_all_exhausted_triggers_ask(self):
        ef = ExecutiveFunction(config={"executive": {"max_retries": 1, "max_pivots": 1}})
        history = [
            {"status": "failed", "reason": "First attempt"},
            {"status": "failed", "reason": "Pivot attempt", "pivot": True},
        ]
        d = ef.review_outcome("Impossible bug", {
            "status": "failed",
            "reason": "All attempts failed",
        }, history=history)
        assert d.action == ExecutiveAction.ASK
        assert d.requires_human

    def test_verification_pending_triggers_ask(self):
        ef = ExecutiveFunction(config={})
        d = ef.review_outcome("Deploy critical fix", {"status": "verification_pending"})
        assert d.action == ExecutiveAction.ASK
        assert d.requires_human

    def test_unknown_status_triggers_abort(self):
        ef = ExecutiveFunction(config={})
        d = ef.review_outcome("Some goal", {"status": "unknown_xyz"})
        assert d.action == ExecutiveAction.ABORT
        assert d.confidence < 0.5

    def test_blocked_status(self):
        ef = ExecutiveFunction(config={})
        d = ef.review_outcome("Build feature", {"status": "blocked", "reason": "Missing credentials"})
        assert d.action == ExecutiveAction.CONTINUE  # First failure → retry
        assert d.frame.get("strategy") == "retry"

    def test_error_status(self):
        ef = ExecutiveFunction(config={})
        d = ef.review_outcome("Run analysis", {"status": "error", "reason": "OOM"})
        assert d.action == ExecutiveAction.CONTINUE
        assert d.frame.get("strategy") == "retry"


# ─── GOAL CONTEXT TESTS ───────────────────────────────────────────────────────

class TestGoalContext:
    def test_create_context(self):
        ef = ExecutiveFunction(config={})
        ctx = ef.create_context("Build the auth module")
        assert ctx.goal_id.startswith("g_")
        assert ctx.goal == "Build the auth module"
        assert ctx.status == "framing"
        assert ctx.attempt_count == 0
        assert ctx.pivot_count == 0

    def test_record_decision_frame(self):
        ef = ExecutiveFunction(config={})
        ctx = ef.create_context("Fix login bug")
        dec = ExecutiveDecision(ExecutiveAction.FRAME, ctx.goal, {"strategy": "direct"}, confidence=0.9)
        ef.record_decision(ctx, dec)
        assert ctx.status == "executing"
        assert ctx.attempt_count == 1
        assert len(ctx.decisions) == 1

    def test_record_decision_pivot(self):
        ef = ExecutiveFunction(config={})
        ctx = ef.create_context("Complex migration")
        ctx.status = "executing"
        dec = ExecutiveDecision(ExecutiveAction.PIVOT, ctx.goal, {}, confidence=0.4)
        ef.record_decision(ctx, dec)
        assert ctx.pivot_count == 1

    def test_record_decision_abort(self):
        ef = ExecutiveFunction(config={})
        ctx = ef.create_context("Bad goal")
        dec = ExecutiveDecision(ExecutiveAction.ABORT, ctx.goal, {}, confidence=0.2)
        ef.record_decision(ctx, dec)
        assert ctx.status == "aborted"

    def test_record_decision_with_memory(self):
        memory = FakeMemory()
        ef = ExecutiveFunction(config={}, memory_store=memory)
        ctx = ef.create_context("Fix login bug")
        dec = ExecutiveDecision(ExecutiveAction.FRAME, ctx.goal, {"strategy": "direct"}, confidence=0.9)
        ef.record_decision(ctx, dec)
        assert len(memory.appended) >= 1
        assert memory.appended[0][0] == "episodic"  # store type

    def test_executive_decision_serialization(self):
        d = ExecutiveDecision(
            action=ExecutiveAction.FRAME,
            goal="Test goal",
            frame={"strategy": "direct"},
            confidence=0.85,
            reasoning=["Simple goal"],
        )
        as_dict = d.to_dict()
        assert as_dict["action"] == "frame"
        assert as_dict["goal"] == "Test goal"
        assert isinstance(as_dict["created_at"], str)

    def test_goal_context_serialization(self):
        ctx = GoalContext(goal_id="g_test", goal="Some goal", status="executing")
        ctx.decisions.append(ExecutiveDecision(ExecutiveAction.FRAME, "Some goal", {}, confidence=0.9))
        as_dict = ctx.to_dict()
        assert as_dict["goal_id"] == "g_test"
        assert len(as_dict["decisions"]) == 1


# ─── CONFIG OVERRIDE TESTS ────────────────────────────────────────────────────

class TestConfigThresholds:
    def test_custom_thresholds(self):
        config = {
            "executive": {
                "max_retries": 5,
                "max_pivots": 3,
                "confidence_continue": 0.7,
                "confidence_ask": 0.2,
            }
        }
        ef = ExecutiveFunction(config=config)
        assert ef.max_retries == 5
        assert ef.max_pivots == 3
        assert ef.conf_continue == 0.7
        assert ef.conf_ask == 0.2

    def test_default_thresholds(self):
        ef = ExecutiveFunction(config={})
        assert ef.max_retries == 3
        assert ef.max_pivots == 2
        assert ef.conf_continue == 0.6
        assert ef.conf_ask == 0.15


# ─── EDGE CASES ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_goal(self):
        ef = ExecutiveFunction(config={})
        d = ef.frame_goal("")
        assert d.action == ExecutiveAction.ASK
        assert d.requires_human

    def test_special_characters_in_goal(self):
        ef = ExecutiveFunction(config={})
        d = ef.frame_goal("eval('__import__(\"os\").system(\"rm -rf /\")')")
        # Should not crash, should assess somehow
        assert isinstance(d, ExecutiveDecision)

    def test_long_string_no_crash(self):
        ef = ExecutiveFunction(config={})
        d = ef.frame_goal(" ".join(["word"] * 500))
        assert isinstance(d, ExecutiveDecision)
        assert d.frame["complexity"] <= 1.0

    def test_memory_append_without_memory_store(self):
        # EF should work without a memory store
        ef = ExecutiveFunction(config={})
        context = ef.create_context("Test")
        dec = ExecutiveDecision(ExecutiveAction.FRAME, "Test", {}, confidence=0.5)
        ef.record_decision(context, dec)  # Should not crash
        assert context.attempt_count == 1

    def test_goal_context_multiple_decisions(self):
        ef = ExecutiveFunction(config={})
        ctx = ef.create_context("Multi-step goal")
        # Start with a FRAME to transition to executing
        frame_dec = ExecutiveDecision(
            ExecutiveAction.FRAME,
            ctx.goal,
            {"strategy": "direct"},
            confidence=0.9,
            reasoning=["Initial framing"],
        )
        ef.record_decision(ctx, frame_dec)
        assert ctx.status == "executing"
        
        for i in range(5):
            dec = ExecutiveDecision(
                ExecutiveAction.CONTINUE,
                ctx.goal,
                {"step": i},
                confidence=0.8 - i * 0.1,
                reasoning=[f"Step {i} completed"],
            )
            ef.record_decision(ctx, dec)
        assert len(ctx.decisions) == 6  # frame + 5 continues

    def test_max_decomposition_limit(self):
        ef = ExecutiveFunction(config={})
        many_tasks = " and then ".join([f"Do task {i}" for i in range(20)])
        d = ef.frame_goal(many_tasks)
        if d.frame.get("sub_goals"):
            assert len(d.frame["sub_goals"]) <= 4
