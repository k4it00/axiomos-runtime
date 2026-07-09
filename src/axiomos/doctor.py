from pathlib import Path
import axiomos
import sys,shutil
from .memory import MemoryStore
from .drivers import DriverRegistry
from .provider_config import provider_status,ensure_provider_config
from .provider_metrics import ProviderMetricsStore
from .redaction import redact
from .config import config_status
from .packages import PackageRegistry
from .tools import tool_doctor
def run_doctor(workspace='.'):
    root=Path(workspace); checks=[]
    def add(n,s,d=''): checks.append({'name':n,'status':s,'detail':d})
    add('python','ok' if sys.version_info>=(3,10) else 'error',sys.version.split()[0]); add('workspace','ok',str(root.resolve())); add('providers_config','ok',str(ensure_provider_config(root)))
    providers=provider_status(root); available=[p for p in providers if p['available']]; add('providers_available','ok' if available else 'warn',f'{len(available)} available')
    add('capability_broker','ok','broker can score provider candidates')
    add('memory','ok',MemoryStore(root).stats()['root']); add('drivers','ok',','.join(d['provider'] for d in DriverRegistry(root).list())); add('git','ok' if shutil.which('git') else 'missing','optional'); add('ffmpeg','ok' if shutil.which('ffmpeg') else 'missing','optional')
    return redact({'status':'ok' if all(c['status'] in {'ok','missing','warn'} for c in checks) else 'error','checks':checks,'providers':providers,'provider_metrics':ProviderMetricsStore(root).summary()})
