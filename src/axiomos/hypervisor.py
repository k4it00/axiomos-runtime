from pathlib import Path
from datetime import datetime, timezone
import uuid,json
from .router import route_prompt
from .policy import evaluate_policy
from .drivers import execute_driver_request
from .memory import MemoryStore
from .redaction import redact
from .receipts import make_receipt, write_receipt
from .capability_broker import explain_broker
from .provider_metrics import ProviderMetricsStore
def _strategy(intent,policy,mode,reasoning):
    if policy['decision']=='blocked': return {'strategy':'blocked','max_passes':0,'reason':'Policy blocked execution.'}
    if policy.get('requires_verification'): return {'strategy':'review_pass' if mode=='max-quality' or reasoning in {'high','maximum'} else 'single_pass_with_verify','max_passes':2,'reason':'Verification required by policy.'}
    return {'strategy':'single_pass','max_passes':1,'reason':'Policy allows single pass.'}
def run_prompt(prompt,*,workspace='.',source='cli',mode='balanced',reasoning='medium',dry_run=True):
    route=route_prompt(prompt); constraints=('dry_run',) if dry_run else ('execution_unlocked',)
    intent={'goal':prompt,'domain':route['domain'],'required_packages':route['packages'],'required_capabilities':tuple(sorted(set([route['domain']]+route['packages']+route['verification']))),'risk':route['risk'],'quality_target':route['quality_target'],'constraints':constraints}
    policy=evaluate_policy(intent,dry_run=dry_run); plan=_strategy(intent,policy,mode,reasoning)
    mem=MemoryStore(workspace); memory_context=mem.attention(prompt).get('selected', [])
    broker_decision=explain_broker(prompt,route,intent,workspace=workspace,dry_run=dry_run)
    driver_request={'driver_request_id':'drv_'+uuid.uuid4().hex[:10],'requested_capabilities':intent['required_capabilities'],'prompt':prompt,'strategy':plan['strategy'],'privacy':'default','dry_run':dry_run,'policy_decision':policy['decision'],'metadata':{'route':route,'memory_context':memory_context,'broker_decision':broker_decision}}
    driver_result=execute_driver_request(driver_request,workspace=workspace)
    ProviderMetricsStore(workspace).append(driver_result.get('provider') or driver_result.get('driver_name') or 'unknown',driver_result.get('status'),driver_result.get('latency_ms'),(driver_result.get('cost') or {}).get('tokens'),None if driver_result.get('status') in {'ok','dry_run'} else driver_result.get('output'))
    executed=(not dry_run) and driver_result.get('status')=='ok'; status='blocked' if policy['decision']=='blocked' else ('executed' if executed else 'dry_run_planned')
    receipt=make_receipt('prompt_run', status, {'transport':{'source':source,'text':prompt},'route':route,'intent':intent,'policy':policy,'broker_decision':broker_decision,'scheduler_plan':plan,'driver_request':driver_request,'driver_result':driver_result,'dry_run':dry_run}, receipt_id='krec_'+uuid.uuid4().hex[:10])
    path=write_receipt(receipt, workspace)
    label='executed' if executed else ('blocked' if status=='blocked' else 'dry_run')
    mem.append('chronicle',f'Prompt {label}: {prompt}',('prompt',route['domain'],label),{'receipt':str(path)})
    mem.append('failure' if status=='blocked' else 'episodic', f"{'Blocked prompt' if status=='blocked' else label.title()+' task'}: {prompt}", ('policy',) if status=='blocked' else (label,route['domain']), {'receipt':str(path),'provider':driver_result.get('provider')})
    return {'status':status,'route':route,'intent':intent,'policy':policy,'broker_decision':broker_decision,'scheduler_plan':plan,'driver_request':redact(driver_request),'driver_result':driver_result,'receipt':receipt,'receipt_path':str(path)}
