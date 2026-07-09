from __future__ import annotations
from pathlib import Path
from .config import ensure_home, load_config, save_config, set_key, append_env_ref, config_status
from .provider_config import add_cloudflare_provider
from .memory import MemoryStore
from .permissions import permission_catalog

def run_setup(*, home=None, dry_run=True, profile="safe"):
    if dry_run:
        return {"status": "dry_run", "message": "Would initialize AxiomOS home/config/env layout.", "home": str(Path(home).expanduser()) if home else "default ~/.axiom", "profile": profile}
    h = ensure_home(home)
    cfg = load_config(h)
    cfg = set_key(cfg, "tools.profile", profile)
    cfg = set_key(cfg, "permissions.profile", profile)
    save_config(cfg, h)
    return {"status": "ok", "home": str(h), "profile": profile, "config": config_status(h)}

def setup_cloudflare_provider(name, account_env, token_env, *, workspace=".", home=None, model="@cf/meta/llama-3.2-3b-instruct", dry_run=False):
    if dry_run:
        return {"status": "dry_run", "provider": name, "account_env": account_env, "token_env": token_env}
    ensure_home(home)
    append_env_ref(account_env, home=home)
    append_env_ref(token_env, home=home)
    added = add_cloudflare_provider(name, account_env, token_env, workspace=workspace, model=model)
    cfg = load_config(home)
    cfg = set_key(cfg, "provider.default", name)
    save_config(cfg, home)
    return {"status": "ok", "provider": added, "env_refs": [account_env, token_env]}

def setup_memory(*, home=None, workspace=".", enabled=True, attention_limit=5, compression_chars=900, dry_run=False):
    if dry_run:
        return {"status": "dry_run", "memory": {"enabled": enabled, "attention_limit": attention_limit, "compression_chars": compression_chars}}
    ensure_home(home)
    cfg = load_config(home)
    cfg = set_key(cfg, "memory.enabled", str(enabled).lower())
    cfg = set_key(cfg, "memory.attention_limit", str(attention_limit))
    cfg = set_key(cfg, "memory.compression_chars", str(compression_chars))
    save_config(cfg, home)
    store = MemoryStore(workspace)
    store.set_setting("enabled", enabled)
    store.set_setting("attention_limit", attention_limit)
    store.set_setting("compression_chars", compression_chars)
    return {"status": "ok", "memory": store.stats()}

def setup_permissions(profile="safe", *, home=None, dry_run=False):
    profiles = {
        "safe": {"allow": ["filesystem.list", "filesystem.read", "git.status"], "deny": ["shell_full", "network", "external_effect"]},
        "dev": {"allow": ["filesystem.list", "filesystem.read", "filesystem.write", "git.status", "git.diff", "shell.run"], "deny": ["network", "external_effect"]},
        "power": {"allow": ["filesystem.*", "git.*", "shell.run", "browser.*", "mcp.*"], "deny": ["external_effect"]},
    }
    if profile not in profiles:
        raise ValueError(f"Unknown permission profile: {profile}")
    if dry_run:
        return {"status": "dry_run", "profile": profile, **profiles[profile]}
    ensure_home(home)
    cfg = load_config(home)
    cfg = set_key(cfg, "tools.profile", profile)
    cfg = set_key(cfg, "permissions.profile", profile)
    cfg["tools"]["allow"] = profiles[profile]["allow"]
    cfg["tools"]["deny"] = profiles[profile]["deny"]
    save_config(cfg, home)
    return {"status": "ok", "profile": profile, "permissions": permission_catalog(), "tools": profiles[profile]}
