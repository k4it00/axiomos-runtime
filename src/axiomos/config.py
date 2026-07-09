from __future__ import annotations
from pathlib import Path
from typing import Any
import os, yaml

DEFAULT_CONFIG = {
    "runtime": {"version": "1.1", "default_workspace": ".", "dry_run_default": True},
    "provider": {"default": None, "config_path": "configs/providers.yaml"},
    "memory": {"enabled": True, "attention_limit": 5, "compression_chars": 900},
    "tools": {"profile": "safe", "allow": ["filesystem.list", "filesystem.read", "git.status"], "deny": ["shell_full", "network", "external_effect"]},
    "permissions": {"profile": "safe", "human_gate": ["write_file", "git_write", "shell_full", "network", "external_effect"]},
    "identity": {"project": "AxiomOS", "description": "A cognitive hypervisor runtime."},
}

def axiom_home() -> Path:
    return Path(os.environ.get("AXIOM_HOME", str(Path.home() / ".axiom"))).expanduser()

def config_path(home=None) -> Path:
    return (Path(home).expanduser() if home else axiom_home()) / "config.yaml"

def env_path(home=None) -> Path:
    return (Path(home).expanduser() if home else axiom_home()) / ".env"

def ensure_home(home=None) -> Path:
    h = Path(home).expanduser() if home else axiom_home()
    h.mkdir(parents=True, exist_ok=True)
    for sub in ("identity", "memory", "packages", "receipts", "skills", "cron"):
        (h / sub).mkdir(parents=True, exist_ok=True)
    if not config_path(h).exists():
        save_config(DEFAULT_CONFIG, h)
    if not env_path(h).exists():
        env_path(h).write_text("# AxiomOS local secrets. Do not commit.\n", encoding="utf-8")
    return h

def _deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def load_config(home=None):
    h = ensure_home(home)
    data = yaml.safe_load(config_path(h).read_text(encoding="utf-8")) or {}
    return _deep_merge(DEFAULT_CONFIG, data)

def save_config(data, home=None):
    h = Path(home).expanduser() if home else axiom_home()
    h.mkdir(parents=True, exist_ok=True)
    config_path(h).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path(h)

def get_key(data, dotted):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(dotted)
        cur = cur[part]
    return cur

def _coerce(v):
    if isinstance(v, str):
        if v.lower() == "true": return True
        if v.lower() == "false": return False
        if v.lower() in {"none", "null"}: return None
        try: return int(v)
        except ValueError: return v
    return v

def set_key(data, dotted, value):
    cur = data
    parts = dotted.split(".")
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = _coerce(value)
    return data

def append_env_ref(name, value="", home=None):
    h = ensure_home(home)
    p = env_path(h)
    current = p.read_text(encoding="utf-8")
    if f"{name}=" not in current:
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{name}={value or ''}\n")
    return p

def config_status(home=None):
    h = ensure_home(home)
    return {
        "home": str(h),
        "config": str(config_path(h)),
        "env": str(env_path(h)),
        "dirs": {s: str(h/s) for s in ("identity", "memory", "packages", "receipts", "skills", "cron")},
        "exists": {"config": config_path(h).exists(), "env": env_path(h).exists()},
    }
