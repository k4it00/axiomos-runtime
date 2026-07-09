from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import json, subprocess, shutil, uuid, os

from .permissions import PermissionKernel
from .redaction import redact
from .receipts import make_receipt, write_receipt

@dataclass(frozen=True)
class ToolRequest:
    tool: str
    action: str
    args: dict[str, Any]
    dry_run: bool = True
    human_approved: bool = False
    source: str = "cli"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class ToolResult:
    tool: str
    action: str
    status: str
    output: Any
    evidence: tuple[str, ...]
    permission: dict[str, Any]
    dry_run: bool
    receipt_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class ToolDriver:
    name = "base"
    actions: tuple[str, ...] = ()
    def execute(self, request: ToolRequest, workspace=".") -> ToolResult:
        raise NotImplementedError

def _safe_path(workspace: str | Path, rel: str | Path) -> Path:
    root = Path(workspace).resolve()
    target = (root / rel).resolve()
    if root != target and root not in target.parents:
        raise PermissionError("Path escapes workspace")
    return target

class FilesystemDriver(ToolDriver):
    name = "filesystem"
    actions = ("list", "read", "write")

    def execute(self, request: ToolRequest, workspace=".") -> ToolResult:
        action = request.action
        permission = "list_dir" if action == "list" else ("read_file" if action == "read" else "write_file")
        decision = PermissionKernel(workspace).evaluate(permission, dry_run=request.dry_run, human_approved=request.human_approved)
        if not decision.allowed:
            return ToolResult(self.name, action, "blocked", decision.reason, ("permission_blocked",), decision.to_dict(), request.dry_run)
        path = _safe_path(workspace, request.args.get("path", "."))
        if request.dry_run:
            return ToolResult(self.name, action, "dry_run", f"Would run filesystem.{action} on {path}", ("external_effects=0",), decision.to_dict(), True)
        if action == "list":
            if not path.exists():
                return ToolResult(self.name, action, "error", "path_not_found", ("filesystem_checked",), decision.to_dict(), False)
            output = sorted([p.name for p in path.iterdir()])
        elif action == "read":
            if not path.exists() or not path.is_file():
                return ToolResult(self.name, action, "error", "file_not_found", ("filesystem_checked",), decision.to_dict(), False)
            output = path.read_text(encoding="utf-8", errors="replace")
        elif action == "write":
            content = str(request.args.get("content", ""))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            output = f"wrote {len(content)} chars"
        else:
            output = "unknown_action"
        return ToolResult(self.name, action, "ok", redact(output), ("filesystem_action=1",), decision.to_dict(), False)

class GitDriver(ToolDriver):
    name = "git"
    actions = ("status", "diff", "log")

    def execute(self, request: ToolRequest, workspace=".") -> ToolResult:
        decision = PermissionKernel(workspace).evaluate("git_read", dry_run=request.dry_run, human_approved=request.human_approved)
        if not decision.allowed:
            return ToolResult(self.name, request.action, "blocked", decision.reason, ("permission_blocked",), decision.to_dict(), request.dry_run)
        if request.dry_run:
            return ToolResult(self.name, request.action, "dry_run", f"Would run git.{request.action}", ("external_effects=0",), decision.to_dict(), True)
        if not shutil.which("git"):
            return ToolResult(self.name, request.action, "error", "git_not_found", ("git_checked",), decision.to_dict(), False)
        cmd = {
            "status": ["git", "status", "--short"],
            "diff": ["git", "diff", "--stat"],
            "log": ["git", "log", "--oneline", "-5"],
        }.get(request.action)
        if not cmd:
            return ToolResult(self.name, request.action, "error", "unknown_action", ("git_checked",), decision.to_dict(), False)
        proc = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, timeout=20)
        output = proc.stdout if proc.returncode == 0 else proc.stderr
        return ToolResult(self.name, request.action, "ok" if proc.returncode == 0 else "error", redact(output), ("git_command=1",), decision.to_dict(), False)

class ShellDriver(ToolDriver):
    name = "shell"
    actions = ("run",)
    ALLOWLIST = {"pwd", "ls", "echo", "python --version", "git status --short"}

    def execute(self, request: ToolRequest, workspace=".") -> ToolResult:
        command = str(request.args.get("command", "")).strip()
        limited = command in self.ALLOWLIST
        permission = "shell_limited" if limited else "shell_full"
        decision = PermissionKernel(workspace).evaluate(permission, dry_run=request.dry_run, human_approved=request.human_approved)
        if not decision.allowed:
            return ToolResult(self.name, "run", "blocked", decision.reason, ("permission_blocked",), decision.to_dict(), request.dry_run)
        if request.dry_run:
            return ToolResult(self.name, "run", "dry_run", f"Would run shell command: {command}", ("external_effects=0",), decision.to_dict(), True)
        if not limited:
            return ToolResult(self.name, "run", "blocked", "command_not_allowlisted", ("shell_safety=1",), decision.to_dict(), False)
        proc = subprocess.run(command, cwd=workspace, shell=True, capture_output=True, text=True, timeout=20)
        output = proc.stdout if proc.returncode == 0 else proc.stderr
        return ToolResult(self.name, "run", "ok" if proc.returncode == 0 else "error", redact(output), ("shell_command=1",), decision.to_dict(), False)

class ToolRegistry:
    def __init__(self):
        self.drivers = {
            "filesystem": FilesystemDriver(),
            "git": GitDriver(),
            "shell": ShellDriver(),
        }

    def list(self) -> list[dict[str, Any]]:
        return [{"name": name, "actions": list(driver.actions)} for name, driver in self.drivers.items()]

    def get(self, tool: str) -> ToolDriver:
        if tool not in self.drivers:
            raise KeyError(f"Unknown tool driver: {tool}")
        return self.drivers[tool]

def _write_tool_receipt(result: ToolResult, request: ToolRequest, workspace=".") -> Path:
    out = Path(workspace) / "axiom_runs"
    out.mkdir(parents=True, exist_ok=True)
    receipt = make_receipt("tool_result", result.status, {"request": request.to_dict(), "result": result.to_dict()}, receipt_id="tool_" + uuid.uuid4().hex[:10])
    return write_receipt(receipt, workspace)

def execute_tool(request: ToolRequest, workspace=".") -> dict[str, Any]:
    try:
        driver = ToolRegistry().get(request.tool)
        result = driver.execute(request, workspace=workspace)
        path = _write_tool_receipt(result, request, workspace=workspace)
        data = result.to_dict()
        data["receipt_path"] = str(path)
        return redact(data)
    except Exception as exc:
        result = ToolResult(request.tool, request.action, "error", str(exc), ("tool_error=1",), {"allowed": False, "reason": "exception"}, request.dry_run)
        path = _write_tool_receipt(result, request, workspace=workspace)
        data = result.to_dict()
        data["receipt_path"] = str(path)
        return redact(data)

def parse_tool_name(name: str) -> tuple[str, str]:
    if "." not in name:
        raise ValueError("Tool name must be tool.action, e.g. filesystem.list")
    tool, action = name.split(".", 1)
    return tool, action

def tool_doctor(workspace=".") -> dict[str, Any]:
    rows = []
    reg = ToolRegistry()
    for d in reg.list():
        rows.append({"tool": d["name"], "status": "ok", "actions": d["actions"]})
    rows.append({"tool": "git_binary", "status": "ok" if shutil.which("git") else "missing"})
    return {"status": "ok", "tools": rows}
