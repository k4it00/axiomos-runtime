from pathlib import Path
from axiomos.tools import ToolRequest, execute_tool, ToolRegistry, tool_doctor
from axiomos.permissions import PermissionKernel
from axiomos.package_tool_bridge import package_tool_needs, run_package_doctor_tools
from axiomos.packages import PackageRegistry

def test_tool_registry():
    tools = ToolRegistry().list()
    assert any(t["name"] == "filesystem" for t in tools)
    assert any(t["name"] == "git" for t in tools)
    assert any(t["name"] == "shell" for t in tools)

def test_filesystem_dry_run_and_execute(tmp_path):
    result = execute_tool(ToolRequest("filesystem", "list", {"path": "."}, dry_run=True), workspace=tmp_path)
    assert result["status"] == "dry_run"
    real = execute_tool(ToolRequest("filesystem", "list", {"path": "."}, dry_run=False), workspace=tmp_path)
    assert real["status"] == "ok"
    assert Path(real["receipt_path"]).exists()

def test_workspace_escape_blocked(tmp_path):
    result = execute_tool(ToolRequest("filesystem", "read", {"path": "../outside.txt"}, dry_run=False), workspace=tmp_path)
    assert result["status"] == "error"

def test_permission_human_gate():
    decision = PermissionKernel().evaluate("write_file", dry_run=False, human_approved=False)
    assert decision.allowed is False
    assert decision.requires_human_gate is True

def test_package_tool_bridge(tmp_path):
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "axiom_package.yaml").write_text('name: demo\nversion: 0.1.0\ncapabilities: [demo]\ndrivers: [filesystem]\npermissions: [filesystem]\npolicies: [safe]\n', encoding="utf-8")
    reg = PackageRegistry(tmp_path)
    reg.install(src)
    needs = package_tool_needs("demo", workspace=tmp_path)
    assert needs["needs"][0]["tool"] == "filesystem"
    doctor = run_package_doctor_tools("demo", workspace=tmp_path)
    assert doctor["tool_results"]
