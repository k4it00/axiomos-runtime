AXIOMOS_IDENTITY = """You are responding inside AxiomOS Runtime.
AxiomOS is a cognitive hypervisor and operating-system-like runtime for LLMs, tools, agents, memory, packages, loops, providers, and future reasoning engines.
AxiomOS is not an embedded operating system. It coordinates cognition, execution, verification, memory, provider drivers, receipts, and policy.
Core principles: Evidence over confidence. Memory is not context; Attention selects memory. Models and tools are drivers under the Hypervisor. Receipts are stronger than logs.
"""
def build_system_messages(route=None, memory_context=None):
    content=AXIOMOS_IDENTITY
    if route: content += f"\nCurrent route/domain: {route.get('domain')}."
    if memory_context:
        rows=[f"- {m.get('type')}: {m.get('content')}" for m in memory_context[-5:]]
        if rows: content += "\nRelevant memory:\n" + "\n".join(rows)
    return [{"role":"system","content":content}]
