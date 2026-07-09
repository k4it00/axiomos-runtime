from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

PERMISSIONS = {
    "read_file": "Read files inside workspace.",
    "write_file": "Write files inside workspace.",
    "list_dir": "List directories inside workspace.",
    "git_read": "Read Git status/log/diff.",
    "git_write": "Change Git repository state.",
    "shell_limited": "Run allowlisted shell commands.",
    "shell_full": "Run arbitrary shell commands.",
    "network": "Use network tools.",
    "external_effect": "Cause irreversible or external side effects.",
}

HUMAN_GATE_PERMISSIONS = {"write_file", "git_write", "shell_full", "network", "external_effect"}

@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requires_human_gate: bool
    permission: str
    reason: str
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class PermissionKernel:
    def __init__(self, workspace="."):
        self.workspace = workspace

    def evaluate(self, permission: str, *, dry_run: bool = True, human_approved: bool = False) -> PermissionDecision:
        if permission not in PERMISSIONS:
            return PermissionDecision(False, False, permission, "unknown_permission", dry_run)
        if dry_run:
            return PermissionDecision(True, False, permission, "dry_run_allowed", dry_run)
        requires = permission in HUMAN_GATE_PERMISSIONS
        if requires and not human_approved:
            return PermissionDecision(False, True, permission, "human_gate_required", dry_run)
        return PermissionDecision(True, requires, permission, "allowed", dry_run)

def permission_catalog() -> dict[str, str]:
    return dict(PERMISSIONS)
