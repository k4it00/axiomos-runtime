from dataclasses import dataclass
import time
from .provider_config import load_provider_specs, load_config, env_available
from .redaction import redact
@dataclass
class ProviderCandidate:
    spec:object; available:bool; reason:str
class ProviderPool:
    def __init__(self,workspace="."):
        self.workspace=workspace; self.specs=load_provider_specs(workspace); self.active=load_config(workspace).get("active_provider")
    def candidates(self,capabilities=(),privacy="default"):
        rows=[]
        for s in self.specs:
            if not s.enabled: rows.append(ProviderCandidate(s,False,"disabled")); continue
            if self.active and s.name!=self.active: rows.append(ProviderCandidate(s,False,"not_active")); continue
            if privacy=="local" and s.type!="dry_run": rows.append(ProviderCandidate(s,False,"privacy_requires_local")); continue
            if s.capabilities and not all(c in s.capabilities for c in capabilities): rows.append(ProviderCandidate(s,False,"capability_mismatch")); continue
            if s.type!="dry_run" and not env_available(s.api_key_ref): rows.append(ProviderCandidate(s,False,"missing_env_ref")); continue
            rows.append(ProviderCandidate(s,True,"available"))
        if self.active and not any(c.available for c in rows):
            for s in self.specs:
                if s.enabled and (not s.capabilities or all(c in s.capabilities for c in capabilities)) and (s.type=="dry_run" or env_available(s.api_key_ref)):
                    rows.append(ProviderCandidate(s,True,"fallback_available")); break
        return rows
    def select(self,capabilities=(),privacy="default"):
        rows=self.candidates(capabilities,privacy)
        for c in rows:
            if c.available: return c.spec
        raise LookupError(f"No provider available: {redact([{'provider':c.spec.name,'reason':c.reason} for c in rows])}")
def timed_call(fn):
    start=time.perf_counter()
    try: return fn(), round((time.perf_counter()-start)*1000,2), None
    except Exception as exc: return None, round((time.perf_counter()-start)*1000,2), exc
