from pathlib import Path
from datetime import datetime, timezone
import json
class ProviderMetricsStore:
    def __init__(self, workspace='.'):
        self.path=Path(workspace)/'.axiom'/'provider_metrics.jsonl'; self.path.parent.mkdir(parents=True,exist_ok=True); self.path.touch(exist_ok=True)
    def append(self, provider, status, latency_ms=None, tokens=None, error=None):
        rec={'provider':provider,'status':status,'latency_ms':latency_ms,'tokens':tokens,'error':error,'created_at':datetime.now(timezone.utc).isoformat()}
        with self.path.open('a',encoding='utf-8') as f: f.write(json.dumps(rec)+'\n')
        return rec
    def rows(self): return [json.loads(x) for x in self.path.read_text(encoding='utf-8').splitlines() if x.strip()]
    def summary(self):
        data={}
        for r in self.rows():
            p=r.get('provider') or 'unknown'; s=data.setdefault(p,{'success':0,'error':0,'dry_run':0,'latencies':[],'tokens':[]})
            st=r.get('status')
            if st=='ok': s['success']+=1
            elif st=='dry_run': s['dry_run']+=1
            elif st: s['error']+=1
            if isinstance(r.get('latency_ms'),(int,float)): s['latencies'].append(r['latency_ms'])
            if isinstance(r.get('tokens'),int): s['tokens'].append(r['tokens'])
        return {p:{'success':s['success'],'error':s['error'],'dry_run':s['dry_run'],'avg_latency_ms':round(sum(s['latencies'])/len(s['latencies']),2) if s['latencies'] else None,'avg_tokens':round(sum(s['tokens'])/len(s['tokens']),2) if s['tokens'] else None} for p,s in data.items()}
