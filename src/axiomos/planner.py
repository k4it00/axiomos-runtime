def create_plan(graph):
    node_by_id={n['id']:n for n in graph['nodes']}
    steps=[{'task_id':tid,'action':node_by_id[tid]['text'],'owner':node_by_id[tid]['properties'].get('owner','unassigned'),'status':'ready'} for tid in graph['ready_tasks']]
    verification=[{'verify_id':n['id'],'check':n['text'],'required':bool(n['properties'].get('required',False)),'status':'pending'} for n in graph['nodes'] if n['type']=='VERIFY']
    return {'steps':steps,'blocked':graph['blocked_tasks'],'verification':verification}
