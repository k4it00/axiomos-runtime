from pathlib import Path
import os, subprocess, sys
from axiomos.config import ensure_home, load_config, get_key, set_key, save_config, config_status
from axiomos.setup import run_setup, setup_memory, setup_permissions, setup_cloudflare_provider

def test_config_home_layout(tmp_path):
    home = ensure_home(tmp_path / "home")
    status = config_status(home)
    assert status["exists"]["config"]
    assert status["exists"]["env"]
    assert (home / "memory").exists()

def test_config_get_set(tmp_path):
    home = ensure_home(tmp_path / "home")
    data = load_config(home)
    data = set_key(data, "provider.default", "cf_test")
    save_config(data, home)
    assert get_key(load_config(home), "provider.default") == "cf_test"

def test_setup_memory_permissions_provider(tmp_path):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    assert run_setup(home=home, dry_run=True)["status"] == "dry_run"
    assert setup_memory(home=home, workspace=workspace, attention_limit=9)["memory"]["settings"]["attention_limit"] == 9
    assert setup_permissions("dev", home=home)["profile"] == "dev"
    result = setup_cloudflare_provider("cf_test", "CF_ACCOUNT", "CF_TOKEN", workspace=workspace, home=home)
    assert result["status"] == "ok"
    assert "CF_TOKEN" in (home / ".env").read_text()

def test_cli_config_setup(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / "src")
    home = tmp_path / "home"
    cmds = [
        [sys.executable, "-m", "axiomos.cli", "config", "init", "--home", str(home)],
        [sys.executable, "-m", "axiomos.cli", "config", "set", "provider.default", "cf_test", "--home", str(home)],
        [sys.executable, "-m", "axiomos.cli", "config", "get", "provider.default", "--home", str(home)],
        [sys.executable, "-m", "axiomos.cli", "setup", "--dry-run", "--home", str(home)],
    ]
    for cmd in cmds:
        rc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=20)
        assert rc.returncode == 0, rc.stderr
