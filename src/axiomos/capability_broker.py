from dataclasses import dataclass, asdict
from typing import Any
from .provider_config import load_provider_specs, load_config, env_available
from .provider_metrics import ProviderMetricsStore
from .redaction import redact
@dataclass(frozen=True)
class CapabilityRequest:
    domain:str; capabilities:tuple[str,...]; quality:str; privacy:str; budget:str; latency:str; requires_identity:bool=True; dry_run:bool=True
    def to_dict(self): return asdict(self)
@dataclass(frozen=True)
class ProviderScore:
    provider:str; pool:str; score:float; available:bool; reason:str; factors:dict[str,Any]
    def to_dict(self): return asdict(self)
def capability_request_from_intent(intent,dry_run=True):
    return CapabilityRequest(intent.get('domain','general'),tuple(intent.get('required_capabilities',()) or ()),intent.get('quality_target','good'),'default','low' if dry_run or intent.get('risk')!='high' else 'medium','low',True,dry_run)
def _quality(name,q):
    n=name.lower()
    if q in {'high','very_high'} and any(k in n for k in ('deepseek','gemini','gpt','claude')): return 20
    if n.startswith('cf_') or 'cloudflare' in n: return 14
    if 'dry' in n: return 3
    return 10
def _cost(name,budget,typ):
    if typ=='dry_run': return 30
    if budget=='low' and (name.lower().startswith('cf_') or 'cloudflare' in name.lower()): return 25
    return 10 if budget=='low' else 15
def _metrics(name,metrics):
    m=metrics.get(name)
    if not m: return 5
    score=5+min(m.get('success',0),10)-min(m.get('error',0)*2,20)
    avg=m.get('avg_latency_ms')
    if isinstance(avg,(int,float)): score += 5 if avg<1000 else (-5 if avg>5000 else 0)
    return score
class CapabilityBroker:
    def __init__(self,workspace='.'):
        self.workspace=workspace; self.active=load_config(workspace).get('active_provider'); self.specs=load_provider_specs(workspace); self.metrics=ProviderMetricsStore(workspace).summary()
    def score(self,request):
        rows=[]
        for spec in self.specs:
            if not spec.enabled: rows.append(ProviderScore(spec.name,spec.pool,0,False,'disabled',{})); continue
            if request.privacy=='local' and spec.type!='dry_run': rows.append(ProviderScore(spec.name,spec.pool,0,False,'privacy_mismatch',{})); continue
            soft={'conformance check','spec mapping','device smoke test','permission flow review','light review'}
            missing=[c for c in request.capabilities if c not in spec.capabilities and c not in soft]
            if spec.capabilities and missing: rows.append(ProviderScore(spec.name,spec.pool,0,False,'capability_mismatch',{'missing':missing})); continue
            if spec.type!='dry_run' and not env_available(spec.api_key_ref): rows.append(ProviderScore(spec.name,spec.pool,0,False,'missing_env_ref',{})); continue
            factors={'capability':40,'active_bonus':15 if self.active==spec.name else 0,'quality':_quality(spec.name,request.quality),'cost':_cost(spec.name,request.budget,spec.type),'metrics':_metrics(spec.name,self.metrics),'dry_run_fit':20 if request.dry_run and spec.type=='dry_run' else 0,'real_execution_fit':10 if (not request.dry_run and spec.type!='dry_run') else 0}
            rows.append(ProviderScore(spec.name,spec.pool,sum(factors.values()),True,'available',factors))
        rows.sort(key=lambda r:r.score,reverse=True)
        return rows
    def choose(self,request):
        scores=self.score(request); selected=next((s for s in scores if s.available),None)
        return redact({'request':request.to_dict(),'selected_provider':selected.provider if selected else None,'selected_score':selected.score if selected else 0,'fallback_order':[s.provider for s in scores if s.available],'scores':[s.to_dict() for s in scores],'explanation':f"Selected {selected.provider} by capability, budget, quality, active preference, and metrics." if selected else 'No provider matched.'})
def explain_broker(prompt,route,intent,workspace='.',dry_run=True):
    return CapabilityBroker(workspace).choose(capability_request_from_intent(intent,dry_run=dry_run))
