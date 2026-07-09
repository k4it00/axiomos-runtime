from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import os, re, yaml
ENV_SUB_RE=re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}")
@dataclass(frozen=True)
class ProviderSpec:
    name:str; type:str; enabled:bool; base_url:str|None; api_key_ref:str|None; model:str|None; capabilities:tuple[str,...]; pool:str
    def to_dict(self): return asdict(self)
DEFAULT_CONFIG={"active_provider":None,"provider_pools":{"local":{"strategy":"first_available","providers":[{"name":"dry_run","type":"dry_run","enabled":True,"capabilities":["general","writing","mobile","engineering","ai_agents","research","trading","security","axiomos_architecture","general_route"]}]}}}
def config_path(workspace="."): return Path(workspace)/"configs"/"providers.yaml"
def ensure_provider_config(workspace="."):
    p=config_path(workspace); p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists(): p.write_text(yaml.safe_dump(DEFAULT_CONFIG,sort_keys=False),encoding="utf-8")
    return p
def load_config(workspace="."): return yaml.safe_load(ensure_provider_config(workspace).read_text(encoding="utf-8")) or DEFAULT_CONFIG
def save_config(data,workspace="."):
    p=ensure_provider_config(workspace); p.write_text(yaml.safe_dump(data,sort_keys=False),encoding="utf-8"); return p
def _expand(v): return None if v is None else ENV_SUB_RE.sub(lambda m: os.environ.get(m.group("name"), "${"+m.group("name")+"}"), v)
def env_available(ref): return True if not ref else (ref.startswith("env:") and bool(os.environ.get(ref.split(":",1)[1])))
def load_provider_specs(workspace="."):
    data=load_config(workspace); specs=[]
    for pool_name,pool in (data.get("provider_pools") or {}).items():
        for raw in pool.get("providers",[]) or []:
            specs.append(ProviderSpec(str(raw.get("name")),str(raw.get("type","openai_compatible")),bool(raw.get("enabled",True)),_expand(raw.get("base_url")),raw.get("api_key_ref"),raw.get("model"),tuple(raw.get("capabilities",[]) or []),str(pool_name)))
    return specs
def provider_status(workspace="."):
    active=load_config(workspace).get("active_provider"); rows=[]
    for s in load_provider_specs(workspace):
        rows.append({"name":s.name,"pool":s.pool,"type":s.type,"enabled":s.enabled,"active":s.name==active,"available":s.enabled and (s.type=="dry_run" or env_available(s.api_key_ref)),"api_key_ref":s.api_key_ref,"model":s.model,"capabilities":list(s.capabilities)})
    return rows
def set_active_provider(name,workspace="."):
    data=load_config(workspace); names={s.name for s in load_provider_specs(workspace)}
    if name not in names: raise ValueError(f"Unknown provider: {name}")
    data["active_provider"]=name; save_config(data,workspace); return name
def add_cloudflare_provider(name,account_env,token_env,workspace=".",model="@cf/meta/llama-3.2-3b-instruct"):
    data=load_config(workspace); pools=data.setdefault("provider_pools",{}); cf=pools.setdefault("cloudflare",{"strategy":"first_available","providers":[]})
    providers=[p for p in cf.setdefault("providers",[]) if p.get("name")!=name]
    providers.append({"name":name,"type":"openai_compatible","enabled":True,"base_url":f"https://api.cloudflare.com/client/v4/accounts/${{{account_env}}}/ai/v1","api_key_ref":f"env:{token_env}","model":model,"capabilities":["general","writing","mobile","engineering","ai_agents","research","security","axiomos_architecture","general_route"]})
    cf["providers"]=providers; data["active_provider"]=name; save_config(data,workspace); return name
