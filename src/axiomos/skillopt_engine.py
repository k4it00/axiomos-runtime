"""
SkillOpt Engine — Native self-optimization for AxiomOS.

Implements the SkillOpt protocol (arXiv 2605.23904):
  Rollout → Reflect → Edit(bounded) → Validate(held-out gate) → Accept/Reject

Optimizable targets:
  - "constitution" — CONSTITUTION.md rules (add/delete/replace)
  - "config"       — ~/.axiom/memory_settings.json values (REPLACE)
  - "skill"        — axiomos-ef SKILL.md protocol (add/delete/replace)

Usage via CLI:
  axiom train            — Run a full training epoch
  axiom rollout          — Collect trial data
  axiom reflect          — Analyze rollout results
  axiom edit             — Propose a bounded edit
  axiom validate         — Evaluate a staged edit against held-out tasks
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal
import json, os, random, re, shutil, subprocess, sys, uuid


# ─── Constants ───────────────────────────────────────────────────────────────

CONSTITUTION_PATH = Path(__file__).parent.parent.parent / "CONSTITUTION.md"
MEMORY_SETTINGS_PATH = Path.home() / ".axiom" / "memory_settings.json"
SKILL_STATE_DIR = Path.home() / ".axiom" / "skillopt"
SKILL_STATE_FILE = SKILL_STATE_DIR / "state.json"

DEFAULT_MEMORY_SETTINGS = {
    "attention_limit": 5,
    "compression_chars": 900,
    "max_retries": 3,
    "max_pivots": 2,
    "confidence_continue": 0.6,
    "confidence_pivot": 0.3,
    "confidence_ask": 0.15,
}

# ─── Domain Types ────────────────────────────────────────────────────────────


class EditAction(Enum):
    ADD = "add"
    DELETE = "delete"
    REPLACE = "replace"


class TargetKind(Enum):
    CONSTITUTION = "constitution"
    CONFIG = "config"
    SKILL = "skill"


class EditStatus(Enum):
    PROPOSED = "proposed"
    VALIDATING = "validating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


@dataclass
class BoundedEdit:
    """A single bounded edit to an optimizable target artifact."""

    edit_id: str
    target: TargetKind
    action: EditAction
    location: str          # e.g. "rule:3", "key:compression_chars", "section:rollout"
    old_value: str | None  # None for ADD
    new_value: str         # None for DELETE
    rationale: str = ""
    status: EditStatus = EditStatus.PROPOSED
    score_before: float | None = None
    score_after: float | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action"] = self.action.value
        d["target"] = self.target.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BoundedEdit":
        d["action"] = EditAction(d["action"])
        d["target"] = TargetKind(d["target"])
        d["status"] = EditStatus(d["status"])
        return cls(**d)


@dataclass
class TrialResult:
    """Outcome of a single trial execution during rollout."""

    trial_id: str
    task: str
    score: float                # 0.0–1.0
    success: bool
    duration_ms: float
    output: str = ""
    error: str | None = None
    trajectory: list[str] = field(default_factory=list)  # key decision points
    epoch: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrainingEpoch:
    """A single training epoch with rollouts, reflections, and edits."""

    epoch: int
    meta_guidance: str = ""               # cross-epoch longitudinal lessons
    trials: list[TrialResult] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    edit_proposals: list[BoundedEdit] = field(default_factory=list)
    accepted_edits: list[BoundedEdit] = field(default_factory=list)
    avg_score: float = 0.0
    best_score: float = 0.0
    held_out_score_before: float = 0.0
    held_out_score_after: float = 0.0
    passed_validation: bool = False
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["trials"] = [t.to_dict() for t in self.trials]
        d["edit_proposals"] = [e.to_dict() for e in self.edit_proposals]
        d["accepted_edits"] = [e.to_dict() for e in self.accepted_edits]
        return d


@dataclass
class TrainingRun:
    """A full SkillOpt training session (may span multiple epochs)."""

    run_id: str
    target: TargetKind
    training_tasks: list[str] = field(default_factory=list)
    held_out_tasks: list[str] = field(default_factory=list)
    epochs: list[TrainingEpoch] = field(default_factory=list)
    current_epoch: int = 0
    meta_guidance: str = ""               # cumulative across epochs
    skill_edits_history: list[BoundedEdit] = field(default_factory=list)
    status: Literal["idle", "training", "completed", "aborted"] = "idle"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["target"] = self.target.value
        d["epochs"] = [e.to_dict() for e in self.epochs]
        d["skill_edits_history"] = [e.to_dict() for e in self.skill_edits_history]
        return d


# ─── Load / Save State ──────────────────────────────────────────────────────


def load_training_state() -> TrainingRun | None:
    """Load the current training run from disk, if any."""
    if not SKILL_STATE_FILE.exists():
        return None
    try:
        with open(SKILL_STATE_FILE) as f:
            data = json.load(f)
        return _deserialize_run(data)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def save_training_state(run: TrainingRun) -> None:
    """Persist the training run to disk."""
    SKILL_STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SKILL_STATE_FILE, "w") as f:
        json.dump(run.to_dict(), f, indent=2)


def _deserialize_run(data: dict) -> TrainingRun:
    """Rebuild a TrainingRun from its dict form."""
    data["target"] = TargetKind(data["target"])
    data["epochs"] = [
        TrainingEpoch(
            epoch=e["epoch"],
            meta_guidance=e.get("meta_guidance", ""),
            trials=[TrialResult(**t) for t in e.get("trials", [])],
            findings=e.get("findings", []),
            edit_proposals=[
                BoundedEdit.from_dict(ed) for ed in e.get("edit_proposals", [])
            ],
            accepted_edits=[
                BoundedEdit.from_dict(ed) for ed in e.get("accepted_edits", [])
            ],
            avg_score=e.get("avg_score", 0.0),
            best_score=e.get("best_score", 0.0),
            held_out_score_before=e.get("held_out_score_before", 0.0),
            held_out_score_after=e.get("held_out_score_after", 0.0),
            passed_validation=e.get("passed_validation", False),
            started_at=e.get("started_at", ""),
            completed_at=e.get("completed_at", None),
        )
        for e in data.get("epochs", [])
    ]
    data["skill_edits_history"] = [
        BoundedEdit.from_dict(ed) for ed in data.get("skill_edits_history", [])
    ]
    return TrainingRun(**{k: v for k, v in data.items() if k != "epochs" and k != "skill_edits_history"})


# ─── Target Readers / Writers ────────────────────────────────────────────────


def read_constitution() -> list[str]:
    """Read CONSTITUTION.md as a list of rule strings."""
    if not CONSTITUTION_PATH.exists():
        return []
    text = CONSTITUTION_PATH.read_text().strip()
    rules = []
    for line in text.split("\n"):
        line = line.strip()
        if line and re.match(r"^\d+\.", line):
            rules.append(line)
    return rules


def write_constitution(rules: list[str]) -> None:
    """Write a list of rule strings back to CONSTITUTION.md."""
    rule_strip = re.compile(r"^\d+\.\s*")
    content = "# AxiomOS Constitution\n\n" + "\n".join(
        "{}. {}".format(i + 1, rule_strip.sub("", r)) for i, r in enumerate(rules)
    )
    # Re-number and re-wrap into markdown
    CONSTITUTION_PATH.write_text(content + "\n")


def read_config_values() -> dict[str, Any]:
    """Read current config values from memory_settings.json."""
    if not MEMORY_SETTINGS_PATH.exists():
        return dict(DEFAULT_MEMORY_SETTINGS)
    try:
        with open(MEMORY_SETTINGS_PATH) as f:
            data = json.load(f)
        return {**DEFAULT_MEMORY_SETTINGS, **data}
    except (json.JSONDecodeError, ValueError):
        return dict(DEFAULT_MEMORY_SETTINGS)


def write_config_value(key: str, value: Any) -> None:
    """Write a single config key to memory_settings.json."""
    MEMORY_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    current = read_config_values()
    current[key] = value
    with open(MEMORY_SETTINGS_PATH, "w") as f:
        json.dump(current, f, indent=2)


def read_skill_doc() -> str:
    """Read the axiomos-ef skill document (if reachable)."""
    skill_path = (
        Path.home()
        / ".hermes"
        / "skills"
        / "software-development"
        / "axiomos-ef"
        / "SKILL.md"
    )
    if skill_path.exists():
        return skill_path.read_text()
    return ""


# ─── Scorer — how well does AxiomOS handle a task? ─────────────────────────


class TaskScorer:
    """
    Evaluation harness for scoring AxiomOS on a task.

    Uses the existing ExecutiveFunction + Hypervisor pipeline to run a goal,
    then scores the result. This is the validation signal for SkillOpt edits.
    """

    def __init__(self, workspace: str = "."):
        self.workspace = workspace

    def score(self, task: str, goal_shell=None) -> TrialResult:
        """
        Execute a task through the AxiomOS pipeline and score it.

        Returns a TrialResult with a 0.0–1.0 score.
        """
        trial_id = f"t_{uuid.uuid4().hex[:8]}"
        start = datetime.now(timezone.utc)

        if goal_shell:
            try:
                result = goal_shell.submit(task, execute=True)
                score, success, output, error = self._score_result(task, result)
            except Exception as e:
                score, success, output, error = 0.0, False, "", str(e)
        else:
            # Dry-run mode — use heuristic scoring, capture trajectory from EF
            from .executive_function import ExecutiveFunction

            ef = ExecutiveFunction()
            frame = ef.frame_goal(task)
            frame_deets = frame.frame if hasattr(frame, "frame") else {}
            trajectory = [
                f"EF: action={frame.action.value}",
                f"EF: complexity={frame_deets.get('complexity','?'):.2f}",
                f"EF: risk={frame_deets.get('risk','?')}",
                f"EF: vagueness={frame_deets.get('vagueness','?'):.2f}",
                f"EF: reasoning={frame.reasoning[0] if frame.reasoning else 'none'}",
            ]
            score, success, output, error = self._score_heuristic(task, ef_frame=frame)

        duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        return TrialResult(
            trial_id=trial_id,
            task=task,
            score=score,
            success=success,
            duration_ms=duration,
            output=output[:2000] if output else "",
            error=error,
            trajectory=trajectory if not goal_shell else [],
        )

    def _score_result(self, task: str, result: dict) -> tuple[float, bool, str, str | None]:
        """Score based on actual execution output."""
        status = result.get("status", "unknown")
        decision = result.get("decision", {})

        if status == "completed":
            return (1.0, True, "Goal completed successfully", None)
        if status == "blocked":
            # Check if blocked for vagueness — if so, it's correct constitutional behavior
            reasoning = decision.get("reasoning", [])
            reason_text = reasoning[0] if reasoning else ""
            is_vague_block = any(
                kw in reason_text.lower()
                for kw in ["vague", "short", "unclear", "ambiguous"]
            )
            if is_vague_block:
                return (0.6, True, f"Correctly blocked vague goal: {reason_text}", None)
            return (0.3, False, json.dumps(result.get("receipt", {})),
                    reason_text or "Blocked")
        if status in ("passed", "continue"):
            return (0.8, True, "Step passed, continuing", None)
        if status == "aborted":
            return (0.1, False, json.dumps(result),
                    decision.get("reasoning", ["Aborted"])[0])

        return (0.5, True, json.dumps(result), None)

    def _score_heuristic(
        self, task: str, ef_frame=None
    ) -> tuple[float, bool, str, str | None]:
        """
        Heuristic scoring when no live pipeline is available.

        Simulates an EF frame + review based purely on the task string.
        Accepts an optional pre-computed ef_frame to avoid double evaluation.

        Key design: correctly blocked vague/risky goals score ~0.6, not 0.2.
        The constitution says "Cognition Before Execution" — blocking a vague
        goal IS correct constitutional behavior. Only actual execution failures
        should score < 0.5. This prevents SkillOpt from wasting epochs trying
        to "fix" something the EF already handles correctly.
        """
        if ef_frame is not None:
            frame = ef_frame
        else:
            from .executive_function import ExecutiveFunction

            ef = ExecutiveFunction()
            frame = ef.frame_goal(task)

        if frame.action.value == "ask":
            reason = frame.reasoning[0] if frame.reasoning else ""
            # EF correctly blocked — score as competent constitutional behavior
            is_vague = any(
                kw in reason.lower()
                for kw in ["vague", "short", "unclear", "ambiguous"]
            )
            if is_vague:
                return (
                    0.6,
                    True,
                    f"Correctly blocked vague goal: {reason}",
                    None,
                )
            return (0.4, False, f"Blocked by EF: {reason}", None)

        if frame.action.value == "frame":
            complexity = frame.frame.get("complexity", 0.5)
            risk = frame.frame.get("risk", "low")
            vagueness = frame.frame.get("vagueness", 0.0)
            # Penalize only if task is still vague but wasn't blocked
            vagueness_penalty = min(vagueness * 0.3, 0.3)
            score = max(0.4, 1.0 - complexity - vagueness_penalty)
            return (score, score > 0.5, f"Framed: {frame.reasoning[0]}", None)

        return (0.5, True, "Default heuristic", None)


# ─── Rollout Engine ──────────────────────────────────────────────────────────


class RolloutEngine:
    """
    Batch-execute N training tasks and collect scores.

    This is the data-collection phase of SkillOpt:
    > rollout: run 8 trials with current config
    """

    def __init__(self, scorer: TaskScorer | None = None):
        self.scorer = scorer or TaskScorer()

    def run_trials(
        self,
        tasks: list[str],
        epoch: int = 0,
        goal_shell=None,
    ) -> list[TrialResult]:
        """Execute N tasks and return TrialResults."""
        results = []
        for i, task in enumerate(tasks):
            result = self.scorer.score(task, goal_shell=goal_shell)
            result.epoch = epoch
            result.trial_id = f"t_{epoch}_{i}_{uuid.uuid4().hex[:4]}"
            results.append(result)
        return results


# ─── Reflection Engine ───────────────────────────────────────────────────────


class ReflectionEngine:
    """
    Analyze rollout results and extract findings.

    This is the analysis phase of SkillOpt:
    > reflect: findings from N trial batch
    """

    def reflect(self, trials: list[TrialResult], epoch: int = 0) -> TrainingEpoch:
        """
        Analyze a batch of trial results.

        Returns a TrainingEpoch with:
          - findings: list of actionable insights
          - avg_score / best_score
          - Classification of success vs failure patterns
        """
        if not trials:
            return TrainingEpoch(epoch=epoch)

        scores = [t.score for t in trials]
        avg_score = sum(scores) / len(scores)
        best_score = max(scores)
        successes = [t for t in trials if t.success]
        failures = [t for t in trials if not t.success]

        findings = []

        # Pattern: what kinds of tasks fail?
        if failures:
            failing_tasks = [f.task[:100] for f in failures]
            avg_fail_score = sum(f.score for f in failures) / len(failures)
            findings.append(
                f"{len(failures)}/{len(trials)} trials failed "
                f"(avg {avg_fail_score:.2f}): {failing_tasks[:3]}"
            )

        # Pattern: score distribution
        if avg_score < 0.5:
            findings.append(f"Low average score ({avg_score:.2f}) — systemic issue")
        elif avg_score >= 0.8:
            findings.append(f"Strong average score ({avg_score:.2f}) — stable config")

        # Pattern: variance
        if len(scores) > 1:
            variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
            if variance > 0.15:
                findings.append(
                    f"High variance ({variance:.3f}) — inconsistent behavior"
                )

        # Pattern: task categories
        long_tasks = [t for t in trials if len(t.task) > 100]
        short_tasks = [t for t in trials if len(t.task) < 30]
        if long_tasks and all(t.success for t in long_tasks):
            findings.append("Long tasks reliably succeed — decompose working well")
        if short_tasks and not all(t.success for t in short_tasks):
            findings.append("Short/vague tasks failing — vagueness detection may need tuning")

        # Pattern: duration outliers
        durations = [t.duration_ms for t in trials]
        if durations:
            avg_dur = sum(durations) / len(durations)
            slow = [t for t in trials if t.duration_ms > avg_dur * 2]
            if slow:
                findings.append(
                    f"{len(slow)} trials took >2x average ({avg_dur:.0f}ms) — "
                    f"performance outliers: {[s.task[:50] for s in slow]}"
                )

        return TrainingEpoch(
            epoch=epoch,
            trials=trials,
            findings=findings,
            avg_score=avg_score,
            best_score=best_score,
            meta_guidance=self._generate_meta_guidance(findings, avg_score, epoch),
        )

    def _generate_meta_guidance(
        self, findings: list[str], avg_score: float, epoch: int
    ) -> str:
        """Generate a meta-guidance snippet from findings."""
        if not findings:
            return ""

        lines = [f"Epoch {epoch} meta (score: {avg_score:.2f}):"]
        lines.extend(f"  • {f}" for f in findings[:5])
        return "\n".join(lines)


# ─── Edit Proposer ───────────────────────────────────────────────────────────


class EditProposer:
    """
    Propose bounded edits to target artifacts based on findings.

    Bounded = limited number of atomic changes per epoch (learning-rate).
    The 'LR' parameter controls how many edits are allowed per epoch.

    > edit: learning-rate: 2
      proposals:
        - REPLACE rule:3 → "Verification before claim, relaxed for read-only ops"
        - REPLACE key:compression_chars → 1200
    """

    def __init__(self, learning_rate: int = 2, epoch: int = 1):
        self.learning_rate = self._compute_lr(learning_rate, epoch)
        self.base_lr = learning_rate

    @staticmethod
    def _compute_lr(base_lr: int, epoch: int) -> int:
        """
        Cosine decay LR schedule across epochs.

        Matches the SkillOpt paper (arXiv 2605.23904) cosine schedule:
        - Epoch 1: full LR (base_lr edits)
        - Epoch N: base_lr * 0.5 * (1 + cos(N*pi / max_epochs))
        - Effect: aggressive early, conservative later

        Default max_epochs = 10 for the cosine period.
        """
        if epoch <= 1:
            return base_lr
        max_epochs = 10
        import math

        decay = 0.5 * (1 + math.cos((epoch - 1) * math.pi / max_epochs))
        return max(1, round(base_lr * decay))

    def propose_edits(
        self, target: TargetKind, findings: list[str], epoch: int = 0
    ) -> list[BoundedEdit]:
        """
        Analyze findings and propose bounded edits to the target.

        Returns a list of BoundedEdit proposals (at most learning_rate).
        """
        proposals: list[BoundedEdit] = []
        used_slots = 0
        current_rules = (
            read_constitution() if target == TargetKind.CONSTITUTION else []
        )

        if target == TargetKind.CONSTITUTION:
            proposals.extend(
                self._propose_constitution_edits(findings, current_rules, used_slots)
            )
        elif target == TargetKind.CONFIG:
            proposals.extend(
                self._propose_config_edits(findings, used_slots)
            )
        elif target == TargetKind.SKILL:
            proposals.extend(
                self._propose_skill_edits(findings, used_slots)
            )

        # Deduplicate: skip edits whose new_value already exists in target
        seen_values = set()
        deduped = []
        for p in proposals:
            key = p.new_value.strip().lower() if p.new_value else ""
            if key and key in seen_values:
                continue
            # Also check if already in the current artifact
            already_present = False
            for rule in current_rules:
                if p.new_value and any(
                    word in rule.lower()
                    for word in p.new_value.lower().split()
                    if len(word) > 3
                ):
                    # Check if it's substantially the same rule
                    overlap = len(
                        set(p.new_value.lower().split())
                        & set(rule.lower().split())
                    )
                    if overlap >= 3:
                        already_present = True
                        break
            if not already_present:
                seen_values.add(key)
                deduped.append(p)

        proposals = deduped[: self.learning_rate]
        for p in proposals:
            p.edit_id = f"e_{epoch}_{uuid.uuid4().hex[:6]}"

        return proposals

    def _propose_constitution_edits(
        self, findings: list[str], current_rules: list[str], used: int
    ) -> list[BoundedEdit]:
        """Generate edits for CONSTITUTION.md based on findings."""
        proposals = []
        current = current_rules  # alias for readability

        for finding in findings:
            if "vague" in finding.lower() or "vagueness" in finding.lower():
                # Suggest adding a rule about vagueness handling
                proposals.append(
                    BoundedEdit(
                        edit_id="",
                        target=TargetKind.CONSTITUTION,
                        action=EditAction.ADD,
                        location="end",
                        old_value=None,
                        new_value="11. Vague goals require decomposition before execution.",
                        rationale="Short/vague tasks failing — add constitutional guidance",
                    )
                )
            if "variance" in finding.lower():
                proposals.append(
                    BoundedEdit(
                        edit_id="",
                        target=TargetKind.CONSTITUTION,
                        action=EditAction.ADD,
                        location="end",
                        old_value=None,
                        new_value="12. Repeated failure on the same pattern warrants a pivot.",
                        rationale="High variance — add fail-pattern recognition rule",
                    )
                )
            if "systemic" in finding.lower():
                # Consider replacing a weak rule
                if len(current) >= 3:
                    proposals.append(
                        BoundedEdit(
                            edit_id="",
                            target=TargetKind.CONSTITUTION,
                            action=EditAction.REPLACE,
                            location=f"rule:3",
                            old_value=current[2] if len(current) > 2 else "",
                            new_value="3. Verification before claim; relaxation permitted for read-only operations.",
                            rationale="Systemic low scores — strengthen verification rule with relaxation",
                        )
                    )

        return proposals

    def _propose_config_edits(
        self, findings: list[str], used: int
    ) -> list[BoundedEdit]:
        """Generate edits for memory_settings.json based on findings."""
        proposals = []
        config = read_config_values()

        for finding in findings:
            if "performance" in finding.lower() and "outlier" in finding.lower():
                # Too aggressive compression causing slow responses?
                current_chars = config.get("compression_chars", 900)
                proposals.append(
                    BoundedEdit(
                        edit_id="",
                        target=TargetKind.CONFIG,
                        action=EditAction.REPLACE,
                        location="key:compression_chars",
                        old_value=str(current_chars),
                        new_value=str(min(current_chars + 300, 2000)),
                        rationale="Performance outliers — increase compression buffer",
                    )
                )
            if "variance" in finding.lower():
                current_confidence = config.get("confidence_continue", 0.6)
                proposals.append(
                    BoundedEdit(
                        edit_id="",
                        target=TargetKind.CONFIG,
                        action=EditAction.REPLACE,
                        location="key:confidence_continue",
                        old_value=str(current_confidence),
                        new_value=str(round(min(current_confidence + 0.1, 0.95), 2)),
                        rationale="High variance — tighten continue confidence",
                    )
                )
            if "vague" in finding.lower() or "vagueness" in finding.lower():
                current_max_retries = config.get("max_retries", 3)
                if current_max_retries > 1:
                    proposals.append(
                        BoundedEdit(
                            edit_id="",
                            target=TargetKind.CONFIG,
                            action=EditAction.REPLACE,
                            location="key:max_retries",
                            old_value=str(current_max_retries),
                            new_value=str(current_max_retries - 1),
                            rationale="Short tasks failing — reduce futile retries, pivot faster",
                        )
                    )

        return proposals

    def _propose_skill_edits(
        self, findings: list[str], used: int
    ) -> list[BoundedEdit]:
        """Generate edits for the axiomos-ef SKILL.md."""
        proposals = []
        skill_text = read_skill_doc()

        for finding in findings:
            if "vague" in finding.lower():
                # Could add a new section or modify existing one
                if "Vague detection" not in skill_text:
                    proposals.append(
                        BoundedEdit(
                            edit_id="",
                            target=TargetKind.SKILL,
                            action=EditAction.ADD,
                            location="section:protocol",
                            old_value=None,
                            new_value=(
                                "## Vague goal handling\n\n"
                                "When EF estimates complexity > 0.5 AND vagueness detected:\n"
                                "1. Request decomposition from user before execution\n"
                                "2. If user refuses, execute with minimum scope\n"
                                "3. Record the refusal in findings"
                            ),
                            rationale="Short/vague tasks failing — add vagueness handling protocol",
                        )
                    )
            if "variance" in finding.lower():
                proposals.append(
                    BoundedEdit(
                        edit_id="",
                        target=TargetKind.SKILL,
                        action=EditAction.ADD,
                        location="section:protocol",
                        old_value=None,
                        new_value=(
                            "## Variance handling\n\n"
                            "When trial variance exceeds 0.15:\n"
                            "1. Increase batch size for more stable estimates\n"
                            "2. Reduce confidence thresholds for pivot decisions\n"
                            "3. Prioritize high-variance task types in next epoch"
                        ),
                        rationale="High variance identified — add stabilization protocol",
                    )
                )

        return proposals


# ─── Edit Applier ────────────────────────────────────────────────────────────


class EditApplier:
    """
    Apply a bounded edit to the target artifact.

    This is the execution phase:
    > edit: apply proposal e_1_abc123
    """

    @staticmethod
    def apply(edit: BoundedEdit) -> bool:
        """Apply a BoundedEdit to its target. Returns True on success."""
        try:
            if edit.target == TargetKind.CONSTITUTION:
                return EditApplier._apply_constitution(edit)
            elif edit.target == TargetKind.CONFIG:
                return EditApplier._apply_config(edit)
            elif edit.target == TargetKind.SKILL:
                return EditApplier._apply_skill(edit)
        except Exception:
            return False

    @staticmethod
    def rollback(edit: BoundedEdit) -> bool:
        """Roll back a previously applied edit. Returns True on success."""
        try:
            if edit.action == EditAction.ADD:
                # Reverse: delete what was added
                rev_edit = BoundedEdit(
                    edit_id=f"rev_{edit.edit_id}",
                    target=edit.target,
                    action=EditAction.DELETE,
                    location=edit.location,
                    old_value=edit.new_value,
                    new_value="",
                    rationale=f"Rollback of {edit.edit_id}",
                )
                return EditApplier.apply(rev_edit)
            elif edit.action == EditAction.DELETE:
                # Reverse: re-add what was deleted
                rev_edit = BoundedEdit(
                    edit_id=f"rev_{edit.edit_id}",
                    target=edit.target,
                    action=EditAction.ADD,
                    location=edit.location,
                    old_value=None,
                    new_value=edit.old_value or "",
                    rationale=f"Rollback of {edit.edit_id}",
                )
                return EditApplier.apply(rev_edit)
            elif edit.action == EditAction.REPLACE:
                # Reverse: swap back
                rev_edit = BoundedEdit(
                    edit_id=f"rev_{edit.edit_id}",
                    target=edit.target,
                    action=EditAction.REPLACE,
                    location=edit.location,
                    old_value=edit.new_value,
                    new_value=edit.old_value or "",
                    rationale=f"Rollback of {edit.edit_id}",
                )
                return EditApplier.apply(rev_edit)
        except Exception:
            return False

    @staticmethod
    def _apply_constitution(edit: BoundedEdit) -> bool:
        rules = read_constitution()

        if edit.action == EditAction.ADD:
            # Append new rule (re-numbered by write_constitution)
            rules.append(edit.new_value)
            write_constitution(rules)
            return True

        elif edit.action == EditAction.DELETE:
            # Find and remove
            target_text = edit.location.replace("rule:", "").strip()
            if target_text.isdigit():
                idx = int(target_text) - 1
                if 0 <= idx < len(rules):
                    rules.pop(idx)
                    write_constitution(rules)
                    return True
            # Try text match
            rules = [r for r in rules if edit.old_value not in r]
            write_constitution(rules)
            return True

        elif edit.action == EditAction.REPLACE:
            target_text = edit.location.replace("rule:", "").strip()
            if target_text.isdigit():
                idx = int(target_text) - 1
                if 0 <= idx < len(rules):
                    rules[idx] = edit.new_value
                    write_constitution(rules)
                    return True
            # Try text match
            rules = [
                edit.new_value if edit.old_value in r else r for r in rules
            ]
            write_constitution(rules)
            return True

        return False

    @staticmethod
    def _apply_config(edit: BoundedEdit) -> bool:
        key = edit.location.replace("key:", "").strip()
        if not key:
            return False

        if edit.action == EditAction.REPLACE:
            # Parse the value type from old_value
            old = edit.old_value
            if old is not None and old.replace(".", "").isdigit():
                if "." in old:
                    write_config_value(key, float(edit.new_value))
                else:
                    write_config_value(key, int(edit.new_value))
            elif old in ("true", "false"):
                write_config_value(key, edit.new_value.lower() == "true")
            else:
                write_config_value(key, edit.new_value)
            return True

        return False

    @staticmethod
    def _apply_skill(edit: BoundedEdit) -> bool:
        """Apply edits to the axiomos-ef SKILL.md."""
        skill_path = (
            Path.home()
            / ".hermes"
            / "skills"
            / "software-development"
            / "axiomos-ef"
            / "SKILL.md"
        )
        if not skill_path.exists():
            return False

        text = skill_path.read_text()

        if edit.action == EditAction.ADD:
            if edit.new_value not in text:
                text += f"\n\n{edit.new_value}\n"
                skill_path.write_text(text)
            return True

        elif edit.action == EditAction.DELETE:
            if edit.old_value and edit.old_value in text:
                text = text.replace(edit.old_value, "")
                skill_path.write_text(text)
                return True

        elif edit.action == EditAction.REPLACE:
            if edit.old_value and edit.old_value in text:
                text = text.replace(edit.old_value, edit.new_value)
                skill_path.write_text(text)
                return True

        return False


# ─── Validation Gate ─────────────────────────────────────────────────────────


class ValidationGate:
    """
    Evaluate proposed edits against held-out tasks.

    This is the acceptance gate:
    > validate: score held-out tasks before and after edit
    """

    def __init__(self, scorer: TaskScorer | None = None):
        self.scorer = scorer or TaskScorer()

    def evaluate(
        self,
        edit: BoundedEdit,
        held_out_tasks: list[str],
        goal_shell=None,
    ) -> tuple[float, float, bool]:
        """
        Evaluate an edit against held-out tasks.

        Returns (score_before, score_after, passed).
        passed = score_after >= score_before (non-degradation).
        """
        # Score before
        before = self._score_tasks(held_out_tasks, goal_shell)
        score_before = before["avg"]

        # Apply edit
        if not EditApplier.apply(edit):
            # If apply failed, return no change
            return (score_before, score_before, False)

        # Score after
        after = self._score_tasks(held_out_tasks, goal_shell)
        score_after = after["avg"]

        # Auto-rollback if score degraded and not a validation run
        if edit.status != EditStatus.VALIDATING and score_after < score_before:
            EditApplier.rollback(edit)
            return (score_before, score_before, False)

        passed = score_after >= score_before
        edit.score_before = score_before
        edit.score_after = score_after

        return (score_before, score_after, passed)

    def _score_tasks(
        self, tasks: list[str], goal_shell=None
    ) -> dict[str, Any]:
        """Score a list of tasks and return aggregate stats."""
        if not tasks:
            return {"avg": 0.5, "count": 0, "scores": []}

        scores = []
        for task in tasks:
            result = self.scorer.score(task, goal_shell=goal_shell)
            scores.append(result.score)

        return {
            "avg": sum(scores) / len(scores),
            "count": len(scores),
            "scores": scores,
        }


# ─── Full Training Loop ──────────────────────────────────────────────────────


class SkillOptLoop:
    """
    Orchestrate a full SkillOpt training session.

    Usage:
        loop = SkillOptLoop(target=TargetKind.CONSTITUTION)
        loop.set_training_tasks(tasks_a)
        loop.set_held_out_tasks(tasks_b)
        result = loop.run_epoch(goal_shell=gs)
    """

    def __init__(
        self,
        target: TargetKind = TargetKind.CONSTITUTION,
        learning_rate: int = 2,
        workspace: str = ".",
    ):
        self.target = target
        self.learning_rate = learning_rate
        self.workspace = workspace
        self.run: TrainingRun | None = None
        self._rolled_out_before_validate = True

    # ── Public API ───────────────────────────────────────────────────────────

    def set_training_tasks(self, tasks: list[str]) -> None:
        """Set the training task set."""
        self._ensure_run()
        self.run.training_tasks = tasks

    def set_held_out_tasks(self, tasks: list[str]) -> None:
        """Set the held-out evaluation tasks."""
        self._ensure_run()
        self.run.held_out_tasks = tasks

    def run_epoch(self, goal_shell=None) -> TrainingEpoch:
        """
        Execute one full training epoch:

          1. Rollout: batch-execute training tasks
          2. Reflect: analyze results
          3. Edit: propose bounded edits based on findings
          4. Validate: evaluate edits against held-out tasks
          5. Accept/Reject: apply accepted edits, compile meta_guidance
        """
        self._ensure_run()
        self.run.status = "training"

        epoch = self.run.current_epoch + 1
        epoch_obj = TrainingEpoch(epoch=epoch)

        # ── 1. Rollout ──
        rollout = RolloutEngine(self._scorer())
        trials = rollout.run_trials(
            self.run.training_tasks, epoch=epoch, goal_shell=goal_shell
        )
        epoch_obj.trials = trials

        # ── 2. Reflect ──
        reflector = ReflectionEngine()
        reflected = reflector.reflect(trials, epoch=epoch)
        epoch_obj.findings = reflected.findings
        epoch_obj.avg_score = reflected.avg_score
        epoch_obj.best_score = reflected.best_score
        epoch_obj.meta_guidance = reflected.meta_guidance

        # ── 3. Edit ──
        proposer = EditProposer(learning_rate=self.learning_rate, epoch=epoch)
        proposals = proposer.propose_edits(
            self.target, reflected.findings, epoch=epoch
        )
        epoch_obj.edit_proposals = proposals

        # ── 4-5. Validate & Accept —─────────────
        if proposals and self.run.held_out_tasks:
            validator = ValidationGate(self._scorer())

            for edit in proposals:
                edit.status = EditStatus.VALIDATING
                score_before, score_after, passed = validator.evaluate(
                    edit, self.run.held_out_tasks, goal_shell=goal_shell
                )

                if passed:
                    edit.status = EditStatus.ACCEPTED
                    epoch_obj.accepted_edits.append(edit)
                    self.run.skill_edits_history.append(edit)
                else:
                    edit.status = EditStatus.REJECTED
                    # Already auto-rolled-back by ValidationGate

            epoch_obj.held_out_score_before = proposals[0].score_before or 0.0
            epoch_obj.held_out_score_after = proposals[0].score_after or 0.0
            epoch_obj.passed_validation = any(
                e.status == EditStatus.ACCEPTED for e in proposals
            )

        elif proposals and not self.run.held_out_tasks:
            # No held-out tasks — auto-accept
            for edit in proposals:
                EditApplier.apply(edit)
                edit.status = EditStatus.ACCEPTED
                epoch_obj.accepted_edits.append(edit)
                self.run.skill_edits_history.append(edit)
            epoch_obj.passed_validation = True

        # ── Compile meta_guidance ──
        guidance_parts = [reflected.meta_guidance] if reflected.meta_guidance else []
        if epoch_obj.accepted_edits:
            guidance_parts.append(
                f"Accepted {len(epoch_obj.accepted_edits)} edits "
                f"(score {epoch_obj.held_out_score_before:.2f} → "
                f"{epoch_obj.held_out_score_after:.2f})"
            )
        epoch_obj.meta_guidance = " | ".join(guidance_parts)

        # Update run-level meta_guidance
        if epoch_obj.meta_guidance:
            if self.run.meta_guidance:
                self.run.meta_guidance += "\n" + epoch_obj.meta_guidance
            else:
                self.run.meta_guidance = epoch_obj.meta_guidance

        epoch_obj.completed_at = datetime.now(timezone.utc).isoformat()
        self.run.epochs.append(epoch_obj)
        self.run.current_epoch = epoch
        self.run.status = "completed"

        # Persist
        save_training_state(self.run)

        return epoch_obj

    def status(self) -> dict[str, Any]:
        """Return current training status."""
        if not self.run:
            return {"status": "idle"}
        return {
            "status": self.run.status,
            "target": self.run.target.value,
            "current_epoch": self.run.current_epoch,
            "total_epochs": len(self.run.epochs),
            "training_tasks": len(self.run.training_tasks),
            "held_out_tasks": len(self.run.held_out_tasks),
            "meta_guidance_length": len(self.run.meta_guidance),
            "skill_edits_count": len(self.run.skill_edits_history),
        }

    def save(self) -> None:
        """Persist current training state."""
        self._ensure_run()
        save_training_state(self.run)

    @classmethod
    def resume(cls, target: TargetKind | None = None) -> "SkillOptLoop":
        """Resume a previous training session from disk."""
        run = load_training_state()
        if run is None:
            return cls(target=target or TargetKind.CONSTITUTION)

        loop = cls(target=run.target)
        loop.run = run
        return loop

    # ── Internal ──────────────────────────────────────────────────────────

    def _ensure_run(self) -> None:
        if self.run is None:
            self.run = TrainingRun(
                run_id=f"so_{uuid.uuid4().hex[:12]}",
                target=self.target,
            )

    def _scorer(self) -> TaskScorer:
        return TaskScorer(workspace=self.workspace)


# ─── Convenience: CLI execution helpers ──────────────────────────────────────


def cmd_status() -> dict[str, Any]:
    """Show current training status."""
    run = load_training_state()
    if run is None:
        return {"status": "idle", "message": "No active training session"}
    loop = SkillOptLoop.resume()
    return loop.status()


def cmd_rollout(
    tasks: list[str],
    target: str = "constitution",
    epoch: int = 1,
) -> list[dict[str, Any]]:
    """Execute a rollout batch and display results."""
    engine = RolloutEngine()
    target_kind = TargetKind(target)
    loop = SkillOptLoop.resume(target=target_kind)
    if loop.run:
        loop.run.training_tasks = tasks
        loop.save()
    results = engine.run_trials(tasks, epoch=epoch)
    return [r.to_dict() for r in results]


def cmd_reflect(trials: list[dict[str, Any]], epoch: int = 1) -> dict[str, Any]:
    """Analyze trial results and return findings."""
    trial_objs = [TrialResult(**t) for t in trials]
    engine = ReflectionEngine()
    epoch_obj = engine.reflect(trial_objs, epoch=epoch)
    return epoch_obj.to_dict()


def cmd_edit(
    target: str = "constitution",
    findings: list[str] | None = None,
    learning_rate: int = 2,
) -> list[dict[str, Any]]:
    """Propose edits based on findings."""
    target_kind = TargetKind(target)
    findings = findings or []
    proposer = EditProposer(learning_rate=learning_rate)
    proposals = proposer.propose_edits(target_kind, findings)
    return [p.to_dict() for p in proposals]


def cmd_validate(
    edit_data: dict[str, Any],
    held_out_tasks: list[str],
) -> dict[str, Any]:
    """Validate an edit against held-out tasks."""
    edit = BoundedEdit.from_dict(edit_data)
    edit.status = EditStatus.VALIDATING
    gate = ValidationGate()
    before, after, passed = gate.evaluate(edit, held_out_tasks)
    return {
        "edit_id": edit.edit_id,
        "score_before": before,
        "score_after": after,
        "passed": passed,
        "target": edit.target.value,
        "location": edit.location,
    }


def cmd_train(
    tasks: list[str],
    held_out: list[str] | None = None,
    target: str = "constitution",
    learning_rate: int = 2,
    goal_shell=None,
) -> dict[str, Any]:
    """Run a full training epoch."""
    target_kind = TargetKind(target)
    loop = SkillOptLoop(target=target_kind, learning_rate=learning_rate)
    loop.set_training_tasks(tasks)
    if held_out:
        loop.set_held_out_tasks(held_out)
    epoch_result = loop.run_epoch(goal_shell=goal_shell)
    return epoch_result.to_dict()
