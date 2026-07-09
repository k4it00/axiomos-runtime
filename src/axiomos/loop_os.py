from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json, uuid

from .loop_runtime import parse_loops_md
from .hypervisor import run_prompt
from .memory import MemoryStore
from .tools import ToolRequest, execute_tool
from .redaction import redact
from .receipts import make_receipt, write_receipt

@dataclass(frozen=True)
class LoopPhaseResult:
    phase: str
    status: str
    output: dict[str, Any]
    def to_dict(self): return asdict(self)

class LoopPlanner:
    def plan(self, loop: dict[str, Any]) -> dict[str, Any]:
        return {
            "goal": loop.get("goal"),
            "action": loop.get("action"),
            "max_passes": loop.get("max_passes", 2),
            "verification": loop.get("acceptance_check"),
            "strategy": "planner_executor_verifier_reflector",
        }

class LoopExecutor:
    def execute(self, plan: dict[str, Any], workspace=".", dry_run=True) -> dict[str, Any]:
        prompt = f"Plan loop action safely: {plan.get('action')}"
        provider_result = run_prompt(prompt, workspace=workspace, dry_run=True)
        tool_result = execute_tool(ToolRequest("filesystem", "list", {"path": "."}, dry_run=True, source="loop_os"), workspace=workspace)
        return {"provider": provider_result, "tool": tool_result, "dry_run": dry_run}

class LoopVerifier:
    def verify(self, loop: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
        check = (loop.get("acceptance_check") or "").lower()
        if any(k in check for k in ("real-device", "device", "emulator", "manual", "external")):
            return {"status": "verification_pending", "reason": "external_or_manual_check_required"}
        if execution.get("provider") and execution.get("tool"):
            return {"status": "passed_dry_run", "reason": "provider_and_tool_dry_run_completed"}
        return {"status": "failed", "reason": "missing_execution_result"}

class LoopReflector:
    def reflect(self, plan: dict[str, Any], execution: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
        if verification["status"] == "passed_dry_run":
            return {"status": "success", "lesson": "Loop completed deterministic dry-run execution path."}
        if verification["status"] == "verification_pending":
            return {"status": "pending", "lesson": "Loop needs external verification before success claim."}
        return {"status": "needs_repair", "lesson": "Loop failed verification and should be repaired or retried."}

class LoopOS:
    def __init__(self, workspace="."):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)

    def run_loop(self, loop: dict[str, Any], *, dry_run=True) -> dict[str, Any]:
        phases: list[LoopPhaseResult] = []
        plan = LoopPlanner().plan(loop)
        phases.append(LoopPhaseResult("plan", "ok", plan))

        execution = LoopExecutor().execute(plan, workspace=self.workspace, dry_run=dry_run)
        phases.append(LoopPhaseResult("execute", "ok", {"provider_status": execution.get("provider", {}).get("status"), "tool_status": execution.get("tool", {}).get("status")}))

        verification = LoopVerifier().verify(loop, execution)
        phases.append(LoopPhaseResult("verify", verification["status"], verification))

        reflection = LoopReflector().reflect(plan, execution, verification)
        phases.append(LoopPhaseResult("reflect", reflection["status"], reflection))

        if reflection["status"] == "success":
            stop_reason = "success"
            status = "success"
        elif reflection["status"] == "pending":
            stop_reason = "verification_pending"
            status = "stopped"
        else:
            stop_reason = "needs_repair"
            status = "stopped"

        self.memory.append("chronicle", f"LoopOS {status}: {loop.get('name')}", ("loop_os", status), {"stop_reason": stop_reason})
        if status != "success":
            self.memory.append("failure", f"LoopOS stopped: {loop.get('name')}", ("loop_os", stop_reason), {"reflection": reflection})
        else:
            self.memory.append("procedural", f"LoopOS success pattern: {loop.get('name')}", ("loop_os", "success"), {"plan": plan})

        receipt = make_receipt("loop_os_run", status, {"loop": loop, "stop_reason": stop_reason, "phases": [p.to_dict() for p in phases], "dry_run": dry_run}, receipt_id="loopos_" + uuid.uuid4().hex[:10])
        path = write_receipt(receipt, self.workspace)
        return {"status": status, "stop_reason": stop_reason, "phases": [p.to_dict() for p in phases], "receipt": receipt, "receipt_path": str(path)}

    def run_file(self, path: str | Path, *, dry_run=True, name: str | None = None) -> dict[str, Any]:
        loops = parse_loops_md(path)
        if name:
            loops = [l for l in loops if l.get("name") == name]
        if not loops:
            return {"status": "blocked", "reason": "no_matching_loop", "runs": []}
        return {"status": "ok", "runs": [self.run_loop(loop, dry_run=dry_run) for loop in loops]}
