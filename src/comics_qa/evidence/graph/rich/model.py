"""Conservative CKG-3 derivations over pinned CKG-1/2 snapshots; no model calls."""
from collections import Counter
from itertools import combinations
import math
from pathlib import Path
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ckg_schema import stable_id, CLOSED
from name_visibility import tokens

SCHEMA = 'comics_qa.ckg3.v1'
VERSION = 'ckg3.1'
POLICY = {'membership_min': .6, 'membership_ambiguity': .3, 'spatial_margin': .05,
          'overlap_iou': .1, 'size_ratio': 1.5,
          'ocr_normalization': 'NFKC+casefold+whitespace+curly_apostrophe; punctuation retained'}
KINDS = {'panels', 'panel_order', 'text_order', 'transcript', 'mention'}
REGISTRY = {
    'panel_on_page': ['Panel', 'Page'], 'in_panel': ['Appearance|Text', 'Panel'],
    'panel_order_rank': ['Panel', 'Int'], 'text_order_rank': ['Text', 'Int'],
    'next_text': ['Text', 'Text'], 'reading_pos': ['Text', 'Int', 'Int', 'Int'],
    'transcript': ['Text', 'Str'], 'name_occurs': ['Text', 'Character', 'Str'],
    'mentions': ['Text', 'Character'], 'left_of': ['Appearance', 'Appearance'],
    'above': ['Appearance', 'Appearance'], 'overlaps': ['Appearance', 'Appearance'],
    'larger_than': ['Appearance', 'Appearance'], 'present_panel': ['Character', 'Panel'],
    'offpanel_line': ['Text', 'Appearance'],
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().replace('’', "'").split())


def area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def valid(node, page):
    b = node.get('box')
    return (isinstance(b, list) and len(b) == 4 and
            all(type(x) in (int, float) and math.isfinite(x) for x in b) and
            0 <= b[0] < b[2] <= page['width'] and 0 <= b[1] < b[3] <= page['height'] and
            not node.get('geometry_review_required', False))


def intersection(a, b):
    return max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))


def record(prefix, data):
    return {**data, 'id': stable_id(prefix + ':', data)}


def build(graph, visibility, sources, decisions=()):
    """No input mutation. Decisions attest exact snapshots, never a model source globally."""
    require(graph['chapter_id'] == visibility['chapter_id'] and graph['page_ids'] == visibility['page_ids'], 'Companion scope mismatch')
    nodes = {n['id']: n for n in graph['nodes']}
    pages = {p: nodes[p] for p in graph['page_ids']}
    coverage = {(c['page_id'], c['family']): c['status'] for c in graph['coverage']}
    reviews = {}; used = set()
    for d in decisions:
        require(isinstance(d, dict) and d.get('kind') in KINDS, 'Unknown review kind')
        key = d['kind'], d['target_id']
        require(key not in reviews, 'Duplicate review decision')
        require(d['chapter_id'] == graph['chapter_id'] and d['page_id'] in pages, 'Wrong review chapter/page')
        require(d['graph_sha256'] == sources['graph_sha256'] and d['visibility_sha256'] == sources['visibility_sha256'] and
                d['image_sha256'] == pages[d['page_id']]['image_sha256'], 'Stale review snapshot/image')
        require(d.get('status') in ('verified', 'rejected') and
                all(isinstance(d.get(k), str) and d[k].strip() for k in ('reviewer', 'note')), 'Review needs verdict, reviewer and note')
        reviews[key] = d

    def decision(kind, target, pid):
        d = reviews.get((kind, target))
        if d:
            require(d['page_id'] == pid, 'Review targets a different page')
            used.add((kind, target))
        return d

    def review_ref(d):
        return stable_id('review:', d) if d else None

    result = {'schema': SCHEMA, 'version': VERSION, 'chapter_id': graph['chapter_id'],
              'split': graph['split'], 'page_ids': graph['page_ids'], 'sources': sources, 'policy': POLICY, 'registry': REGISTRY,
              'panels': [], 'memberships': [], 'transcripts': [], 'mentions': [], 'orders': [],
              'facts': [], 'coverage': [], 'review_queue': [], 'decisions': list(decisions)}

    def queue(kind, target, pid, details):
        result['review_queue'].append({'kind': kind, 'target_id': target, 'page_id': pid, 'details': details,
            'decision_template': {'kind': kind, 'target_id': target, 'chapter_id': graph['chapter_id'], 'page_id': pid,
                'graph_sha256': sources['graph_sha256'], 'visibility_sha256': sources['visibility_sha256'],
                'image_sha256': pages[pid]['image_sha256'], 'status': 'pending', 'reviewer': '', 'note': ''}})

    def fact(rel, args, pid, origin, premises, **extra):
        require(rel in REGISTRY and len(args) == len(REGISTRY[rel]), 'Invalid richer relation')
        for arg, typ in zip(args, REGISTRY[rel]):
            require(type(arg) is int if typ == 'Int' else isinstance(arg, str) if typ == 'Str' else
                    arg in nodes and nodes[arg]['type'] in typ.split('|'), 'Invalid richer fact argument')
        row = record('rf', {'rel': rel, 'args': args, 'page_id': pid, 'origin': origin,
            'answer_eligible': origin in ('H', 'V'), 'premises': sorted(set(premises)),
            'source_snapshots': sources, 'version': VERSION, **extra})
        result['facts'].append(row)
        return row

    members = {}; panel_records = {}; order_records = {}
    for pid, page in pages.items():
        panel_nodes = sorted((n for n in nodes.values() if n['type'] == 'Panel' and n['page_id'] == pid), key=lambda n: n['id'])
        panel_ids = [p['id'] for p in panel_nodes]
        pd = decision('panels', pid, pid)
        if pd and pd['status'] == 'verified':
            require(pd.get('complete_inventory') is True and sorted(pd.get('panel_ids', [])) == panel_ids,
                    'Panel review must confirm the exact complete inventory')
            require(all(valid(p, page) for p in panel_nodes), 'Invalid panel geometry needs upstream correction')
        status = pd['status'] if pd else 'candidate'
        pr = record('panels', {'page_id': pid, 'panel_ids': panel_ids, 'status': status, 'origin': 'V' if status == 'verified' else 'M',
                              'review': review_ref(pd), 'sources': sources})
        result['panels'].append(pr); panel_records[pid] = pr
        if not pd:
            queue('panels', pid, pid, {'panel_ids': panel_ids, 'complete_inventory': True,
                  'instruction': 'Check every panel box and missing/extra panels. Set complete_inventory=true only after full-page review.'})
        for p in panel_nodes:
            fact('panel_on_page', [p['id'], pid], pid, pr['origin'], [pr['id']])
        regions = sorted((n for n in nodes.values() if n['type'] in ('Appearance', 'Text') and n['page_id'] == pid), key=lambda n: n['id'])
        for n in regions:
            fractions = [{'panel_id': p['id'], 'fraction': intersection(n['box'], p['box']) / area(n['box'])}
                         for p in panel_nodes if valid(n, page) and valid(p, page)]
            substantial = [f for f in fractions if f['fraction'] >= POLICY['membership_ambiguity']]
            best = max(fractions, key=lambda f: f['fraction']) if fractions else None
            state = ('invalid_geometry' if not valid(n, page) or any(not valid(p, page) for p in panel_nodes) else
                     'ambiguous' if len(substantial) > 1 else
                     'unique' if best and best['fraction'] >= POLICY['membership_min'] else 'unassigned')
            panel = best['panel_id'] if state == 'unique' else None
            origin = 'V' if panel and status == 'verified' and n['origin'] == 'H' else 'M'
            m = record('membership', {'region_id': n['id'], 'page_id': pid, 'panel_id': panel, 'status': state,
                'fractions': fractions, 'origin': origin, 'answer_eligible': origin == 'V', 'panel_record': pr['id'], 'sources': sources})
            result['memberships'].append(m); members[n['id']] = m
            if panel:
                fact('in_panel', [n['id'], panel], pid, origin, [m['id'], pr['id'], n['id']])

        for kind, expected in [('panel_order', panel_ids), ('text_order', [n['id'] for n in regions if n['type'] == 'Text'])]:
            d = decision(kind, pid, pid)
            if d and d['status'] == 'verified':
                order = d.get('ordered_ids')
                require(isinstance(order, list) and len(order) == len(set(order)) and sorted(order) == sorted(expected), 'Order must be an exact permutation')
                if kind == 'panel_order':
                    require(status == 'verified', 'Verified panel order requires a verified panel inventory')
                else:
                    require(page['annotated'] and coverage.get((pid, 'text_boxes')) in CLOSED, 'Text order needs closed human text-box coverage')
            else:
                order = None
            estimate = sorted(panel_ids, key=lambda x: (nodes[x]['estimated_reading_rank'], x)) if kind == 'panel_order' else None
            row = record('order', {'page_id': pid, 'kind': kind, 'status': d['status'] if d else 'candidate',
                'ordered_ids': order, 'estimated_ids': estimate, 'review': review_ref(d), 'sources': sources})
            result['orders'].append(row); order_records[pid, kind] = row
            if not d:
                queue(kind, pid, pid, {'all_ids': expected, 'estimated_ids': estimate,
                      'instruction': 'Provide ordered_ids as the complete reading-order permutation; IDs are not reading ranks.'})
            if order is not None:
                for rank, nid in enumerate(order):
                    fact(kind + '_rank', [nid, rank], pid, 'V', [row['id']])
                if kind == 'text_order':
                    for a, b in zip(order, order[1:]):
                        fact('next_text', [a, b], pid, 'V', [row['id']])

    transcripts = {}
    for a in visibility['alignments']:
        pid = a['page_id']; tid = a['text_id']
        require(pid in pages and a['image_sha256'] == pages[pid]['image_sha256'], 'Alignment page/image mismatch')
        require(tid is None or tid in nodes and nodes[tid]['type'] == 'Text' and nodes[tid]['page_id'] == pid, 'Invalid alignment text')
        require(a['alignment_id'] not in transcripts, 'Duplicate alignment')
        d = decision('transcript', a['alignment_id'], pid)
        agree = bool(a['status'] == 'aligned' and a['paddle_ok'] and a['magi_ok'] and
                     normalize(a['paddle_text']) and normalize(a['paddle_text']) == normalize(a['magi_text']))
        consensus = normalize(a['paddle_text']) if agree else None
        status = 'verified' if agree else 'candidate'
        if d:
            status = d['status']; consensus = None
            if status == 'verified':
                require(isinstance(d.get('transcription'), str) and normalize(d['transcription']), 'Review requires a nonempty full transcription')
                consensus = normalize(d['transcription'])
        row = record('transcript', {'alignment_id': a['alignment_id'], 'page_id': pid, 'text_id': tid,
            'status': status, 'origin': 'V' if status == 'verified' else 'M', 'consensus': consensus,
            'paddle_text': a['paddle_text'], 'magi_text': a['magi_text'],
            'verification': 'individual_visual_review' if d else 'two_model_full_normalized_agreement' if agree else None,
            'review': review_ref(d), 'sources': a['sources'],
            'quote_eligible': status == 'verified' and tid is not None and nodes[tid]['origin'] == 'H'})
        transcripts[a['alignment_id']] = row; result['transcripts'].append(row)
        if row['quote_eligible']:
            fact('transcript', [tid, consensus], pid, 'V', [row['id']])
        elif not d:
            queue('transcript', a['alignment_id'], pid, {'text_id': tid, 'paddle_text': a['paddle_text'], 'magi_text': a['magi_text'],
                'instruction': 'Provide transcription of the full region, not just a name span.'})

    for e in visibility['evidence']:
        pid, tid = e['page_id'], e['text_id']; tr = transcripts[e['alignment_id']]
        lexical = e['status'] == 'verified' and tid is not None
        semantic = 'candidate'
        d = decision('mention', e['evidence_id'], pid)
        if d:
            semantic = d['status']
            if semantic == 'verified':
                require(lexical and tr['quote_eligible'], 'Semantic mention needs verified lexical evidence and full transcript')
                needle, words = tokens(e['form']), tokens(tr['consensus'])
                require(needle and any(words[i:i+len(needle)] == needle for i in range(len(words)-len(needle)+1)), 'Reviewed mention form missing from transcript')
                require(d.get('identity_id') == e['identity_id'] and not nodes[e['identity_id']]['generic'], 'Review cannot change a mention identity')
        row = record('mention', {'page_id': pid, 'text_id': tid, 'identity_id': e['identity_id'], 'form': e['form'],
            'visibility_evidence_id': e['evidence_id'], 'lexical_status': 'verified' if lexical else e['status'] if e['status'] == 'rejected' else 'candidate',
            'semantic_status': semantic, 'transcript_id': tr['id'], 'review': review_ref(d), 'sources': e['sources']})
        result['mentions'].append(row)
        if lexical:
            fact('name_occurs', [tid, e['identity_id'], e['form']], pid, 'V', [e['evidence_id'], row['id']])
        if semantic == 'verified':
            fact('mentions', [tid, e['identity_id']], pid, 'V', [row['id'], tr['id']])
        elif not d and lexical:
            queue('mention', e['evidence_id'], pid, {'text_id': tid, 'identity_id': e['identity_id'], 'form': e['form'],
                  'instruction': 'Verify that the text refers to this character, rather than using an ordinary word or another referent.'})

    # Panel presence and off-panel speech retain human identity/speaker premises.
    speakers = {}
    for f in graph['facts']:
        if f['answer_eligible'] and f['origin'] in ('H', 'V') and f['rel'] == 'spoken_by':
            speakers.setdefault(f['args'][0], []).append(f)
        if f['answer_eligible'] and f['origin'] in ('H', 'V') and f['rel'] == 'is_char':
            appearance, character = f['args']; m = members.get(appearance)
            if m and m['panel_id']:
                fact('present_panel', [character, m['panel_id']], m['page_id'],
                     'V' if m['answer_eligible'] else 'M', [f['fact_id'], m['id']])
    for tid, links in speakers.items():
        # Multiple speaker appearances must not be silently disambiguated.
        if len(links) != 1:
            continue
        f = links[0]; appearance = f['args'][1]
        mt, ma = members.get(tid), members.get(appearance)
        if mt and ma and mt['panel_id'] and ma['panel_id'] and mt['page_id'] == ma['page_id'] and mt['panel_id'] != ma['panel_id']:
            fact('offpanel_line', [tid, appearance], mt['page_id'],
                 'V' if mt['answer_eligible'] and ma['answer_eligible'] else 'M', [f['fact_id'], mt['id'], ma['id']])

    # Geometry only compares human appearances with unambiguous same-panel membership.
    for pid, page in pages.items():
        apps = sorted((n for n in nodes.values() if n['type'] == 'Appearance' and n['page_id'] == pid and n['origin'] == 'H'), key=lambda n: n['id'])
        for a, b in combinations(apps, 2):
            ma, mb = members[a['id']], members[b['id']]
            if not ma['panel_id'] or ma['panel_id'] != mb['panel_id']:
                continue
            panel = nodes[ma['panel_id']]; box = panel['box']
            origin = 'V' if ma['answer_eligible'] and mb['answer_eligible'] else 'M'
            support = [ma['id'], mb['id'], panel_records[pid]['id'], a['id'], b['id']]
            extra = {'panel_id': panel['id'], 'coordinate_frame': 'original_image_pixels', 'policy': POLICY}
            for axis, rel in [(0, 'left_of'), (1, 'above')]:
                delta = (b['box'][axis] + b['box'][axis+2] - a['box'][axis] - a['box'][axis+2]) / 2
                margin = POLICY['spatial_margin'] * (box[axis+2] - box[axis])
                if abs(delta) > margin:
                    pair = [a['id'], b['id']] if delta > 0 else [b['id'], a['id']]
                    fact(rel, pair, pid, origin, support, margin_px=margin, **extra)
            inter = intersection(a['box'], b['box']); iou = inter/(area(a['box'])+area(b['box'])-inter)
            if iou >= POLICY['overlap_iou']:
                fact('overlaps', [a['id'], b['id']], pid, origin, support, iou=iou, **extra)
            def truncated(n):
                c = n['box']
                return n.get('touches_image_edge', False) or any(c[k] <= box[k] for k in (0, 1)) or any(c[k] >= box[k] for k in (2, 3))
            if not truncated(a) and not truncated(b):
                big, small = sorted((a, b), key=lambda n: area(n['box']), reverse=True)
                ratio = area(big['box'])/area(small['box'])
                if ratio >= POLICY['size_ratio']:
                    fact('larger_than', [big['id'], small['id']], pid, origin, support, area_ratio=ratio, **extra)
        pr = panel_records[pid]
        text_order = order_records[pid, 'text_order']; panel_order = order_records[pid, 'panel_order']
        if text_order['ordered_ids'] is not None and panel_order['ordered_ids'] is not None:
            assigned = [members[t]['panel_id'] for t in text_order['ordered_ids']]
            ranks = [panel_order['ordered_ids'].index(p) for p in assigned if p is not None]
            require(ranks == sorted(ranks), 'Reviewed text order conflicts with panel order')
            # An unassigned/ambiguous text may belong to any panel and change local
            # ordinal ranks. Do not emit exact positions for a partially mapped page.
            complete_mapping = all(members[t]['answer_eligible'] for t in text_order['ordered_ids'])
            local = Counter()
            for tid, panel_id in zip(text_order['ordered_ids'], assigned):
                if complete_mapping and panel_id is not None and members[tid]['answer_eligible']:
                    fact('reading_pos', [tid, page['index_in_chapter'], panel_order['ordered_ids'].index(panel_id), local[panel_id]],
                         pid, 'V', [text_order['id'], panel_order['id'], members[tid]['id']])
                    local[panel_id] += 1
        for family, closed in [('panels', pr['status'] == 'verified'),
                ('panel_memberships', pr['status'] == 'verified' and all(m['answer_eligible'] for m in members.values() if m['page_id'] == pid)),
                ('text_order', text_order['ordered_ids'] is not None),
                ('ocr', coverage.get((pid, 'text_boxes')) in CLOSED and all(any(t['text_id'] == n['id'] and t['quote_eligible'] for t in transcripts.values()) for n in nodes.values() if n['type'] == 'Text' and n['page_id'] == pid)),
                ('semantic_mentions', False), ('spatial', False)]:
            # Membership closure also requires complete human inventories.
            if family == 'panel_memberships':
                closed = closed and all(coverage.get((pid, f)) in CLOSED for f in ('char_boxes', 'text_boxes'))
            inherited = (('char_boxes', 'text_boxes') if family == 'panel_memberships' else
                         ('text_boxes',) if family in ('ocr', 'text_order') else ())
            closed_status = 'closed_verified'
            if any(coverage.get((pid, f)) == 'closed_assumed' for f in inherited):
                closed_status = 'closed_assumed'
            elif any(coverage.get((pid, f)) == 'closed_audited' for f in inherited):
                closed_status = 'closed_audited'
            result['coverage'].append(record('rcov', {'page_id': pid, 'family': family,
                'status': closed_status if closed else 'open',
                'scope': 'supplied_human_text_regions' if family in ('ocr', 'text_order') else 'supplied_page',
                'basis': 'all_required_evidence_verified_and_base_coverage_closed' if closed else 'incomplete_or_unreviewed',
                'base_coverage': [c['coverage_id'] for c in graph['coverage'] if c['page_id'] == pid], 'sources': sources}))
    require(used == set(reviews), 'Unknown/stale review target')
    result['counts'] = {'pages': len(pages), 'facts': len(result['facts']),
        'eligible_facts': sum(f['answer_eligible'] for f in result['facts']),
        'verified_transcripts': sum(t['status'] == 'verified' for t in result['transcripts']),
        'verified_panel_pages': sum(p['status'] == 'verified' for p in result['panels']),
        'verified_text_order_pages': sum(o['kind'] == 'text_order' and o['status'] == 'verified' for o in result['orders']),
        'semantic_mentions': sum(m['semantic_status'] == 'verified' for m in result['mentions']),
        'review_queue': len(result['review_queue'])}
    return result


def eligible_facts(companion, relation):
    """Positive witnesses only. Missing rows never establish false/absence."""
    require(companion['schema'] == SCHEMA, 'Unsupported richer-evidence schema')
    return [f for f in companion['facts'] if f['rel'] == relation and f['answer_eligible'] and f['origin'] in ('H', 'V')]
