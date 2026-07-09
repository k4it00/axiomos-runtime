import json
from .session import AxiomSession
from .commands import dispatch_line
BANNER='AxiomOS Runtime 1.0 Alpha 2\nType /help. Normal text is dry-run by default.\n'
def run_shell():
    s=AxiomSession(); print(BANNER)
    while True:
        try: line=input('axiom> ')
        except (EOFError,KeyboardInterrupt): print(); return 0
        r=dispatch_line(line,s)
        if r.get('status')!='noop': print(json.dumps(r,indent=2))
        if r.get('status')=='exit': return 0
def run_one_shot(prompt,execute=False):
    from .hypervisor import run_prompt
    print(json.dumps(run_prompt(prompt,dry_run=not execute),indent=2)); return 0
