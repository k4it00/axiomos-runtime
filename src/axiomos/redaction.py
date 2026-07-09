from __future__ import annotations
import re
from typing import Any
SECRET_PATTERNS=[re.compile(r"cfut_[A-Za-z0-9_-]{20,}"),re.compile(r"sk-[A-Za-z0-9_-]{16,}"),re.compile(r"github_pat_[A-Za-z0-9_]+"),re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"),re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*[A-Za-z0-9_\-]{8,}")]
ACCOUNT_ID_PATTERN=re.compile(r"\b[a-f0-9]{32}\b", re.I)
def redact_text(v:str)->str:
    out=v
    for p in SECRET_PATTERNS: out=p.sub("[REDACTED_SECRET]", out)
    return ACCOUNT_ID_PATTERN.sub("[REDACTED_ACCOUNT_ID]", out)
def redact(obj:Any)->Any:
    if isinstance(obj,str): return redact_text(obj)
    if isinstance(obj,dict): return {k:redact(v) for k,v in obj.items()}
    if isinstance(obj,list): return [redact(x) for x in obj]
    if isinstance(obj,tuple): return tuple(redact(x) for x in obj)
    return obj
