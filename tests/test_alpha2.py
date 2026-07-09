from pathlib import Path
from axiomos.parser import parse_ax_text
from axiomos.validator import validate_document, has_errors
from axiomos.axiom_ir import emit_ir
from axiomos.provider_config import ensure_provider_config, add_cloudflare_provider, set_active_provider, provider_status
from axiomos.hypervisor import run_prompt
from axiomos.memory import MemoryStore
from axiomos.redaction import redact_text
from axiomos.receipts import list_receipts, show_receipt
from axiomos.loop_runtime import run_loops_file
from axiomos.doctor import run_doctor

def test_pipeline_validator_ir():
    doc=parse_ax_text('AXIOM 0.2\n\nGOAL G1 "Goal"\nSUCCESS S1 "Done"\nTASK T1 "Task"\nVERIFY V1 "Check"\n    required: true\nEDGE G1 -> T1 "decomposes_to"\n')
    assert not has_errors(validate_document(doc))
    assert len(emit_ir(doc).to_dict()["edges"]) == 1

def test_provider_config(tmp_path):
    ensure_provider_config(tmp_path)
    add_cloudflare_provider("cf_test","CF_ACCOUNT","CF_TOKEN",tmp_path)
    assert set_active_provider("cf_test",tmp_path) == "cf_test"
    assert any(r["name"]=="cf_test" for r in provider_status(tmp_path))

def test_redaction():
    assert "cfut_" not in redact_text("cfut_abcdefghijklmnopqrstuvwxyz123456")
    assert "[REDACTED_ACCOUNT_ID]" in redact_text("4375289da5a12bfd82d7684664800a32")

def test_prompt_receipt_memory(tmp_path):
    result=run_prompt("Explain what AxiomOS is in one sentence.", workspace=tmp_path, dry_run=True)
    assert result["status"]=="dry_run_planned"
    assert Path(result["receipt_path"]).exists()
    assert MemoryStore(tmp_path).stats()["counts"]["chronicle"] >= 1
    assert list_receipts(tmp_path)

def test_loop_and_doctor(tmp_path):
    loops=tmp_path/"LOOPS.md"
    loops.write_text('# LOOPS.md\n\n## Demo\n\n### Goal\n\nDo it.\n\n### Action\n\nInspect.\n\n### Acceptance Check\n\nDry-run receipt exists.\n\n### Stop Condition\n\nStop after 2 passes.\n', encoding="utf-8")
    assert run_loops_file(loops, workspace=tmp_path)["status"]=="ok"
    assert run_doctor(tmp_path)["status"]=="ok"
