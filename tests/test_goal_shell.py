"""
Tests for GoalShell — the goal lifecycle orchestrator.
"""
from __future__ import annotations
import json, sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from axiomos.goal_shell import GoalShell
from axiomos.executive_function import ExecutiveAction


class TestGoalShell:
    def test_submit_simple_goal(self):
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        result = shell.submit("List all files in the current directory")
        assert result["status"] in ("completed", "continue", "blocked")
        assert "decision" in result
        assert "goal_context" in result

    def test_submit_vague_goal_blocks(self):
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        result = shell.submit("do something")
        assert result["status"] == "blocked"
        assert result["human_prompt"] is not None

    def test_submit_empty_goal(self):
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        result = shell.submit("")
        assert result["status"] == "blocked"

    def test_submit_goal_with_memory_context(self):
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        result = shell.submit("Update the README with project status")
        assert "decision" in result
        assert result["goal_context"]["goal"] == "Update the README with project status"

    def test_goal_shell_tracks_active_goals(self):
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        shell.submit("Fix bug in parser")
        shell.submit("Add new feature")
        assert shell.active_count() >= 1
        statuses = shell.status()
        assert len(statuses) >= 1
        # Each context should have at least one decision recorded
        for ctx in statuses:
            assert len(ctx["decisions"]) >= 1

    def test_multiple_submits_produce_unique_contexts(self):
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        r1 = shell.submit("First goal")
        r2 = shell.submit("Second goal")
        ctx_ids = [r1["goal_context"]["goal_id"], r2["goal_context"]["goal_id"]]
        assert len(set(ctx_ids)) == 2  # Unique IDs

    def test_high_risk_goal_without_context_blocks(self):
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        result = shell.submit("Deploy to production")
        # High risk with no memory context should block
        assert result["status"] == "blocked"
        assert result["human_prompt"] is not None

    def test_verdict_for_simple_goal(self):
        """EF should frame simple goals for direct execution."""
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        result = shell.submit("Read the current directory structure")
        # Should not crash, should return a valid result
        assert isinstance(result, dict)
        assert "decision" in result

    def test_goal_context_includes_framing(self):
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        result = shell.submit("Check Python version")
        ctx = result["goal_context"]
        # Should have at least the framing decision
        assert len(ctx["decisions"]) >= 1
        first_dec = ctx["decisions"][0]
        assert first_dec["action"] in ("frame", "ask")  # ASK for vague, FRAME for ok

    def test_goal_shell_works_without_memory(self):
        shell = GoalShell(workspace=str(Path(__file__).resolve().parents[1]))
        result = shell.submit("Simple task")
        assert "decision" in result
