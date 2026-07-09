from pathlib import Path
import os, subprocess, sys
from axiomos.about import about_payload, read_doc

def test_about_payload_docs_exist():
    payload = about_payload()
    assert payload["version"] == "1.1.0-dev0"
    assert payload["docs"]["PROJECT_STATUS.md"]
    assert "Hypervisor" in payload["architecture"]

def test_read_project_status():
    text = read_doc("status")
    assert "AxiomOS Runtime 1.0 Final" in text
    assert "AxiomOS Runtime 1.1 Dev" in text

def test_cli_about():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    rc = subprocess.run([sys.executable, "-m", "axiomos.cli", "about"], cwd=root, env=env, capture_output=True, text=True, timeout=20)
    assert rc.returncode == 0
    assert "AxiomOS Runtime" in rc.stdout
