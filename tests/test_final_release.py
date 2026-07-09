import json
import os
import subprocess
import sys
from pathlib import Path

import axiomos
from axiomos.provider_config import add_cloudflare_provider, provider_status
from axiomos.capability_broker import explain_broker
from axiomos.router import route_prompt
from axiomos.hypervisor import run_prompt
from axiomos.receipts import show_receipt, validate_receipt_schema

def test_final_version():
    assert axiomos.__version__ == "1.1.0-dev0"

def test_compile_alias_cli(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    rc = subprocess.run(
        [sys.executable, "-m", "axiomos.cli", "compile", str(root / "examples/sample.ax")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert rc.returncode == 0
    assert "compiled" in rc.stdout

def test_provider_fallback_when_active_missing_env(tmp_path):
    add_cloudflare_provider("cf_missing", "MISSING_ACCOUNT_ENV", "MISSING_TOKEN_ENV", tmp_path)
    route = route_prompt("Explain AxiomOS in one sentence.")
    intent = {
        "goal": "Explain AxiomOS",
        "domain": route["domain"],
        "required_packages": route["packages"],
        "required_capabilities": tuple(sorted(set([route["domain"]] + route["packages"] + route["verification"]))),
        "risk": route["risk"],
        "quality_target": route["quality_target"],
        "constraints": ("execution_unlocked",),
    }
    decision = explain_broker("Explain AxiomOS", route, intent, workspace=tmp_path, dry_run=False)
    # Missing external provider should not be selected; dry_run fallback remains available.
    assert decision["selected_provider"] in {"dry_run", None} or "cf_missing" not in decision["fallback_order"]

def test_final_prompt_receipt_schema(tmp_path):
    result = run_prompt("Explain AxiomOS in one sentence.", workspace=tmp_path, dry_run=True)
    receipt = show_receipt(result["receipt_path"])
    assert not validate_receipt_schema(receipt)
    assert receipt["type"] == "prompt_run"
