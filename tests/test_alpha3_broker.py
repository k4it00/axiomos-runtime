from axiomos.router import route_prompt
from axiomos.capability_broker import explain_broker
from axiomos.provider_config import add_cloudflare_provider
from axiomos.hypervisor import run_prompt
from axiomos.provider_metrics import ProviderMetricsStore

def test_broker_selects_dry_run(tmp_path):
    route=route_prompt('Explain AxiomOS in one sentence.')
    intent={'goal':'Explain AxiomOS','domain':route['domain'],'required_packages':route['packages'],'required_capabilities':tuple(sorted(set([route['domain']]+route['packages']+route['verification']))),'risk':route['risk'],'quality_target':route['quality_target'],'constraints':('dry_run',)}
    decision=explain_broker('Explain AxiomOS',route,intent,workspace=tmp_path,dry_run=True)
    assert decision['selected_provider']=='dry_run'

def test_hypervisor_receipt_contains_broker(tmp_path):
    result=run_prompt('Explain AxiomOS in one sentence.', workspace=tmp_path, dry_run=True)
    assert 'broker_decision' in result['receipt']
    assert ProviderMetricsStore(tmp_path).summary()
