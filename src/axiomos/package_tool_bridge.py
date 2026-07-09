from __future__ import annotations
from typing import Any
from .packages import PackageRegistry
from .tools import ToolRequest, execute_tool

PACKAGE_TOOL_MAP = {
    "filesystem": ("filesystem", "list"),
    "adb": ("shell", "run"),
    "gradle": ("shell", "run"),
    "git": ("git", "status"),
    "browser": ("shell", "run"),
}

def package_tool_needs(package_name: str, workspace=".") -> dict[str, Any]:
    pkg = PackageRegistry(workspace).get(package_name)
    needs = []
    for driver in pkg.get("drivers", []):
        mapped = PACKAGE_TOOL_MAP.get(driver)
        needs.append({"declared_driver": driver, "tool": mapped[0] if mapped else None, "action": mapped[1] if mapped else None, "available": bool(mapped)})
    return {"package": package_name, "needs": needs}

def run_package_doctor_tools(package_name: str, workspace=".", dry_run=True) -> dict[str, Any]:
    needs = package_tool_needs(package_name, workspace)
    results = []
    for item in needs["needs"]:
        if not item["available"]:
            results.append({**item, "status": "missing_tool_mapping"})
            continue
        args = {"path": "."} if item["tool"] == "filesystem" else {"command": "echo package tool dry-run"}
        req = ToolRequest(item["tool"], item["action"], args, dry_run=dry_run, source=f"package:{package_name}")
        results.append({**item, "result": execute_tool(req, workspace=workspace)})
    return {"package": package_name, "tool_results": results}
