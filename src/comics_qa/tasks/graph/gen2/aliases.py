"""Snapshot-bound reviewed alias eligibility; never infer human approvals."""
from .quality import normalized,form_is_visible
from ..generation.policy import stable


def validate_reviews(rows,graph,visibility,graph_sha,visibility_sha):
    nodes={n['id']:n for n in graph['nodes']};evidence={e['evidence_id']:e for e in visibility['evidence']}
    approved=[];seen=set()
    for row in rows:
        if row.get('chapter_id')!=graph['chapter_id']:continue
        cid=row.get('identity_id');form=row.get('form');key=(cid,normalized(form))
        if key in seen:raise ValueError('Duplicate alias review')
        seen.add(key)
        if row.get('graph_sha256')!=graph_sha or row.get('visibility_sha256')!=visibility_sha:raise ValueError('Stale alias review snapshot')
        node=nodes.get(cid)
        if not node or node['type']!='Character' or node['generic'] or not isinstance(form,str) or not normalized(form):raise ValueError('Invalid alias identity/form')
        if normalized(form) not in {normalized(x) for x in [node['canonical_name'],*node['aliases']]}:raise ValueError('Review cannot create an unregistered alias')
        if row.get('decision') not in ('pending','approved','rejected'):raise ValueError('Unknown alias review decision')
        if row['decision']!='approved':continue
        if not all(isinstance(row.get(k),str) and row[k].strip() for k in ('reviewer','note')):raise ValueError('Approval needs reviewer and justification')
        if row.get('name_use')!='character_name':raise ValueError('Approval must verify use as a character name, not a word fragment')
        ids=row.get('evidence_ids')
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):raise ValueError('Approval needs distinct visibility evidence IDs')
        for eid in ids:
            e=evidence.get(eid)
            if not e or e['identity_id']!=cid or e['status']!='verified' or normalized(e['form'])!=normalized(form):raise ValueError('Alias evidence does not verify this exact form')
        if not form_is_visible(visibility,cid,form):raise ValueError('Approved alias is not readable')
        approved.append({**row,'review_sha256':stable(row)})
    return approved
