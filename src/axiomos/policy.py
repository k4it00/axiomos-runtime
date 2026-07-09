from .redaction import redact_text
def evaluate_policy(intent,*,dry_run=True):
    blocked=[]
    if redact_text(intent.get('goal','')) != intent.get('goal',''): blocked.append('raw_secret_detected')
    req=intent.get('risk') in {'medium','high','critical'} or intent.get('quality_target') in {'high','very_high'}
    if not dry_run and 'execution_unlocked' not in intent.get('constraints',()): blocked.append('execution_not_unlocked')
    return {'decision':'blocked' if blocked else ('requires_verification' if req else 'allowed'),'allowed':not blocked,'requires_verification':req,'blocked_reasons':blocked,'findings':[]}
