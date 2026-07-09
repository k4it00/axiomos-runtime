import json
import subprocess
import sys
import os
from pathlib import Path

from axiomos.parser import parse_ax_text
from axiomos.validator import validate_document, has_errors
from axiomos.graph import build_graph, detect_cycles
from axiomos.redaction import redact
from axiomos.receipts import show_receipt, validate_receipt_schema
from axiomos.hypervisor import run_prompt
from axiomos.tools import ToolRequest, execute_tool
from axiomos.packages import PackageRegistry
from axiomos.loop_os import LoopOS
import axiomos

def test_version_rc1():
    assert axiomos.__version__ == "1.1.0-dev0"

def test_parser_edge_cases():
    malformed = parse_ax_text('AXIOM 0.2\nEDGE A - B\n')
    assert has_errors(validate_document(malformed))
    dup = parse_ax_text('AXIOM 0.2\nTASK T1 "a"\nTASK T1 "b"\n')
    assert has_errors(validate_document(dup))
    empty = parse_ax_text('AXIOM 0.2\n')
    assert not has_errors(validate_document(empty))

def test_graph_cycle_detection():
    doc = parse_ax_text('AXIOM 0.2\nTASK A "a"\n    depends_on: [B]\nTASK B "b"\n    depends_on: [A]\n')
    graph = build_graph(doc)
    assert detect_cycles(graph)

def test_redaction_nested():
    obj = {"x": ["cfut_abcdefghijklmnopqrstuvwxyz123456", {"acct": "4375289da5a12bfd82d7684664800a32"}]}
    text = json.dumps(redact(obj))
    assert "cfut_" not in text
    assert "4375289" not in text

def test_receipt_schema_roundtrip(tmp_path):
    prompt = run_prompt("Explain AxiomOS in one sentence.", workspace=tmp_path, dry_run=True)
    receipt = show_receipt(prompt["receipt_path"])
    assert not validate_receipt_schema(receipt)

    tool = execute_tool(ToolRequest("filesystem", "list", {"path": "."}, dry_run=False), workspace=tmp_path)
    receipt = show_receipt(tool["receipt_path"])
    assert not validate_receipt_schema(receipt)

    pkg_src = tmp_path / "pkg"
    pkg_src.mkdir()
    (pkg_src / "axiom_package.yaml").write_text("name: demo\nversion: 0.1.0\ncapabilities: [demo]\npermissions: [list_dir]\npolicies: [safe]\n", encoding="utf-8")
    installed = PackageRegistry(tmp_path).install(pkg_src)
    receipt = show_receipt(installed["receipt_path"])
    assert not validate_receipt_schema(receipt)

def test_loop_os_receipt_schema(tmp_path):
    loops = tmp_path / "LOOPS.md"
    loops.write_text("# LOOPS.md\n\n## Demo\n\n### Goal\n\nRun.\n\n### Action\n\nInspect.\n\n### Acceptance Check\n\nDry-run receipt exists.\n\n### Stop Condition\n\nStop after 2 passes.\n", encoding="utf-8")
    result = LoopOS(tmp_path).run_file(loops, dry_run=True)
    receipt = show_receipt(result["runs"][0]["receipt_path"])
    assert not validate_receipt_schema(receipt)

def test_cli_version_and_memory_attention(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    rc = subprocess.run([sys.executable, "-m", "axiomos.cli", "version"], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=20)
    assert rc.returncode == 0
    assert "1.1.0-dev0" in rc.stdout
