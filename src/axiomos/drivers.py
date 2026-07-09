import os,json
from .identity import build_system_messages
from .provider_pool import ProviderPool,timed_call
from .provider_config import load_provider_specs
from .redaction import redact
class DriverError(RuntimeError): pass
DEFAULT_CAPABILITIES={'general','writing','mobile','engineering','ai_agents','research','trading','security','device smoke test','permission flow review','conformance check','spec mapping','light review','axiomos_architecture','general_route'}
class DryRunDriver:
    name='dry_run'; privacy='local'; capabilities=DEFAULT_CAPABILITIES
    def supports(self,caps): return all(c in self.capabilities for c in caps)
    def execute(self,request): return {'driver_name':self.name,'provider':'dry_run','status':'dry_run','output':'DryRunDriver accepted request. No model/tool/external action executed.','evidence':['external_calls=0','tools_executed=0'],'cost':{'tokens':0,'usd':0.0},'latency_ms':0,'metadata':{'identity_injected':True,'strategy':request.get('strategy')}}
class OpenAICompatibleDriver:
    name='openai_compatible'; privacy='external'
    def __init__(self,spec): self.spec=spec; self.capabilities=set(spec.capabilities) or DEFAULT_CAPABILITIES
    def supports(self,caps): return all(c in self.capabilities for c in caps)
    def execute(self,request):
        if request.get('dry_run',True): return {'driver_name':self.name,'provider':self.spec.name,'status':'dry_run','output':'Provider configured but dry_run=true, so no external call was made.','evidence':['external_calls=0'],'cost':{'tokens':0,'usd':0.0},'latency_ms':0,'metadata':{'model':self.spec.model,'identity_injected':True}}
        if not self.spec.api_key_ref or not self.spec.api_key_ref.startswith('env:'): raise DriverError(f'Provider {self.spec.name} must use env: API key ref')
        env_name=self.spec.api_key_ref.split(':',1)[1]; api_key=os.environ.get(env_name)
        if not api_key: raise DriverError(f'Missing env var: {env_name}')
        try: import requests
        except Exception as exc: raise DriverError("Install optional dependency: pip install 'axiomos-runtime[providers]'") from exc
        route=request.get('metadata',{}).get('route',{}); memory_context=request.get('metadata',{}).get('memory_context',[])
        payload={'model':self.spec.model,'messages':build_system_messages(route=route,memory_context=memory_context)+[{'role':'user','content':request['prompt']}]}
        def call():
            resp=requests.post(f"{self.spec.base_url.rstrip('/')}/chat/completions",headers={'Authorization':f'Bearer {api_key}','Content-Type':'application/json'},data=json.dumps(payload),timeout=60); resp.raise_for_status(); return resp.json()
        data,lat,error=timed_call(call)
        if error: raise DriverError(f'Provider {self.spec.name} failed: {error}')
        output=data.get('choices',[{}])[0].get('message',{}).get('content','')
        return redact({'driver_name':self.name,'provider':self.spec.name,'status':'ok','output':output,'evidence':['external_model_call=1','identity_injected=1'],'cost':{'tokens':data.get('usage',{}).get('total_tokens'),'usd':None},'latency_ms':lat,'metadata':{'model':self.spec.model,'provider_pool':self.spec.pool,'identity_injected':True}})
class DriverRegistry:
    def __init__(self,workspace='.'): self.workspace=workspace; self.pool=ProviderPool(workspace); self.dry=DryRunDriver()
    def list(self):
        rows=[{'name':'dry_run','provider':'dry_run','privacy':'local','capabilities':sorted(self.dry.capabilities),'available':True}]
        for c in self.pool.candidates(tuple()): rows.append(redact({'name':c.spec.type,'provider':c.spec.name,'pool':c.spec.pool,'privacy':'external' if c.spec.type!='dry_run' else 'local','capabilities':sorted(c.spec.capabilities),'available':c.available,'reason':c.reason,'model':c.spec.model,'api_key_ref':c.spec.api_key_ref}))
        return rows
    def select(self,caps,privacy='default',dry_run=True,broker_decision=None):
        if dry_run: return self.dry
        selected=(broker_decision or {}).get('selected_provider')
        if selected:
            for spec in load_provider_specs(self.workspace):
                if spec.name==selected:
                    if spec.type=='dry_run': return self.dry
                    if spec.type=='openai_compatible': return OpenAICompatibleDriver(spec)
        spec=self.pool.select(tuple(caps),privacy)
        if spec.type=='dry_run': return self.dry
        if spec.type=='openai_compatible': return OpenAICompatibleDriver(spec)
        raise DriverError(f'Unsupported provider type: {spec.type}')
def execute_driver_request(request,workspace='.'):
    if request.get('policy_decision')=='blocked' or request.get('strategy')=='blocked': return {'driver_name':'none','provider':None,'status':'blocked','output':'Policy blocked driver execution.','evidence':['policy_blocked=true'],'cost':{'tokens':0,'usd':0.0},'metadata':{}}
    try: return redact(DriverRegistry(workspace).select(request.get('requested_capabilities',()),request.get('privacy','default'),request.get('dry_run',True),request.get('metadata',{}).get('broker_decision')).execute(request))
    except Exception as exc: return {'driver_name':'none','provider':None,'status':'error','output':str(redact(str(exc))),'evidence':['driver_error=1'],'cost':{'tokens':0,'usd':0.0},'metadata':{}}
