from pathlib import Path
from axiomos.hypervisor import run_prompt
from axiomos.memory import MemoryStore
from axiomos.packages import PackageRegistry
from axiomos.tools import ToolRequest, execute_tool
from axiomos.loop_os import LoopOS
from axiomos.doctor import run_doctor

def test_integrated_prompt_memory_tool_package_loopos(tmp_path):
    store = MemoryStore(tmp_path)
    store.append("identity", "AxiomOS is a cognitive hypervisor runtime.", ("axiomos",), importance=1.0)

    prompt = run_prompt("Explain AxiomOS in one sentence.", workspace=tmp_path, dry_run=True)
    assert prompt["status"] == "dry_run_planned"
    assert prompt["driver_request"]["metadata"]["memory_context"]

    tool = execute_tool(ToolRequest("filesystem", "list", {"path": "."}, dry_run=False), workspace=tmp_path)
    assert tool["status"] == "ok"

    pkg_src = tmp_path / "pkg"
    pkg_src.mkdir()
    (pkg_src / "axiom_package.yaml").write_text("name: demo\nversion: 0.1.0\ncapabilities: [demo]\ndrivers: [filesystem]\npermissions: [list_dir]\npolicies: [safe]\n", encoding="utf-8")
    reg = PackageRegistry(tmp_path)
    reg.install(pkg_src)
    assert reg.get("demo")["name"] == "demo"

    loops = tmp_path / "LOOPS.md"
    loops.write_text("# LOOPS.md\n\n## Demo Loop\n\n### Goal\n\nRun integrated loop.\n\n### Action\n\nInspect workspace.\n\n### Acceptance Check\n\nDry-run receipt exists.\n\n### Stop Condition\n\nStop after 2 passes.\n", encoding="utf-8")
    loop = LoopOS(tmp_path).run_file(loops, dry_run=True)
    assert loop["status"] == "ok"
    assert loop["runs"][0]["receipt_path"]

    assert run_doctor(tmp_path)["status"] == "ok"
