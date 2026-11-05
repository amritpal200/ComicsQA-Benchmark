"""Free QA generation from chapter evidence packs (expansion plan X3/X4; idea 8B of Free_QA_generation.md).

prepare (CPU): one text pack per request (level page/window/selection/chapter) with short IDs and provenance tags,
               plus the private ID map; requests.json holds pack text, prompt and ID map.
run     (local GPU, user-run): OpenAI-compatible chat endpoint (local vLLM, Qwen3-VL-32B); one create-only file each.
ingest  (CPU): parse the JSON items, validate every typed claim with freegen_check (separate implementation), and
               publish accepted items as story_item.1 records (track=experimental, needs_human_verification,
               needs_uniqueness_check) in a story_store.1 store with a per-reason rejection report.
"""
import json
import re
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .io import digest, member, publish, read, separate, stable
from .story_families import DEFAULTS as STORY_DEFAULTS, STORE, World, key

VERSION = 'freegen.1'
REQUESTS = 'comics_qa.benchmark1000.freegen_requests.1'
LEVELS = ('page', 'window', 'selection', 'chapter')
CLAIMS = ('SAYS', 'ON_PAGE', 'DRAWN', 'NOT_DRAWN', 'SILENT', 'BEFORE', 'NEXT_LINE', 'EVENT', 'FIRST_DRAWN')
ANSWER_FORMATS = ('character', 'page', 'line', 'line_sequence')

PROMPT = """You write questions for a manga reading-comprehension benchmark. Below is an evidence pack for one chapter
(or part of it). The person answering will see ALL page images of the chapter, but NOT this pack.

Write {n} varied, interesting question-answer items that need reading the story across panels and pages. Prefer
questions that combine 2-4 facts from different pages. Mix answer formats: character, page, line, line_sequence.

Rules:
- Use only facts in the pack. Every item lists its reasoning as typed claims over pack IDs.
- Claim types: SAYS(L,C) line L is spoken by C; ON_PAGE(L,P); DRAWN(C,P); NOT_DRAWN(C,P); SILENT(C,P) C has no line on P;
  BEFORE(L1,L2) L1 comes before L2; NEXT_LINE(L1,L2) L2 is the next text after L1 on the same page;
  EVENT(E,C) event E is done by C; FIRST_DRAWN(C,P) C is first drawn on P.
- answer_ref is the pack ID of the answer (a C, P or L ID), or for line_sequence a list of L IDs in the correct order.
- In the question, refer to characters only by their names as written in the CHARACTERS table, to lines only by quoting
  lines marked * exactly, and to pages only if the question states the page number. Never write pack IDs in the question.
- Never put the answer in the question. Do not ask yes/no questions. Avoid the two most frequent characters as answers.
- No feelings, motives or causes unless an EVENT states them.

Return only a JSON list: [{{"question": "...", "answer_format": "character|page|line|line_sequence",
"answer_ref": "C3" or ["L4.2","L9.1"], "claims": ["SAYS(L4.2,C3)", "..."]}}, ...]

EVIDENCE PACK
{pack}
"""


def ids_for(w, order, events):
    """Stable short IDs: C (readable named identities), P (1-based page index), L (texts per page in reading order), E."""
    chars = sorted(w.names, key=lambda c: (-len(w.presence[c]), c))
    cid = {c: f'C{i + 1}' for i, c in enumerate(chars)}
    pid = {p: f'P{i + 1}' for i, p in enumerate(w.g['page_ids'])}
    by_page = defaultdict(list)
    for tid, (page, k) in order.items(): by_page[page].append((k, tid))
    lid = {}
    for page, rows in by_page.items():
        for n, (_, tid) in enumerate(sorted(rows)): lid[tid] = f'L{w.pos[page]}.{n + 1}'
    eid = {e['fact_id']: f'E{i + 1}' for i, e in enumerate(sorted(events, key=lambda e: (w.pos[e['page_id']], e['fact_id'])))}
    return cid, pid, lid, eid


def build_pack(w, order, events, pages, quotable, level):
    cid, pid, lid, eid = ids_for(w, order, events)
    transcripts = {t['text_id']: t for t in w.transcripts if t.get('text_id')}
    out = [f"CHAPTER {w.g['chapter_id']}  pages={len(w.g['page_ids'])}  level={level}  pack_pages={','.join(pid[p][1:] for p in pages)}",
           'CHARACTERS (readable names; pages drawn)']
    for c, short in sorted(cid.items(), key=lambda x: int(x[1][1:])):
        forms = sorted(set(w.forms(c)) - {w.names[c]})
        out.append(f"  {short} {w.names[c]}" + (f" (also written: {', '.join(forms)})" if forms else '') +
                   f"  pages: {','.join(str(w.pos[p]) for p in sorted(w.presence[c], key=w.pos.get))}")
    by_page = defaultdict(list)
    for tid, (page, k) in order.items(): by_page[page].append((k, tid))
    ev_by_page = defaultdict(list)
    for e in events: ev_by_page[e['page_id']].append(e)
    for p in pages:
        drawn = sorted((cid[c] for c in w.identified(p) if c in cid), key=lambda s: int(s[1:]))
        others = len(w.on_page_ids[p]) - len(drawn)
        cov = {f: w.coverage.get((p, f), {}).get('status', 'open') for f in ('char_boxes', 'speaker_links', 'text_boxes')}
        out.append(f"PAGE {pid[p]}  drawn: {' '.join(drawn) or '-'}" + (f" (+{others} unnamed/unreadable)" if others > 0 else '') +
                   f"  [H; characters {cov['char_boxes']}, speakers {cov['speaker_links']}]")
        for _, tid in sorted(by_page[p]):
            t = transcripts.get(tid, {})
            text = t.get('consensus') or t.get('paddle_text') or t.get('magi_text') or ''
            tag = 'V' if t.get('quote_eligible') else 'A'
            who, _ = w.speaker(tid)
            spk = cid.get(who, 'unnamed' if who else '?') if tid in w.is_line else 'not dialogue'
            out.append(f"  {lid[tid]}{'*' if tid in quotable else ''} \"{' '.join(text.split())}\" speaker={spk} [text {tag}; order M]")
        for e in ev_by_page[p]:
            if e['identity_id'] in cid:
                out.append(f"  {eid[e['fact_id']]} EVENT {cid[e['identity_id']]}: {e['statement'].replace('the outlined character', 'this character')} [A, AI-audited]")
    return '\n'.join(out), {'C': {v: k for k, v in cid.items()}, 'P': {v: k for k, v in pid.items()},
                            'L': {v: k for k, v in lid.items()}, 'E': {v: k for k, v in eid.items()}}


def choose_pages(w, level, cfg, n):
    pages = w.g['page_ids']; picks = []
    if level == 'chapter': return [pages]
    if level == 'page':
        rich = sorted((p for p in pages if len(w.identified(p)) >= 2), key=lambda p: key(cfg['seed'], 'fg-p', p))
        return [[p] for p in rich[:n]]
    if level == 'window':
        size = cfg['window']
        starts = sorted(range(0, max(1, len(pages) - size + 1)), key=lambda i: key(cfg['seed'], 'fg-w', i))
        return [pages[i:i + size] for i in starts[:n]]
    pairs = sorted(((a, b) for a in w.names for b in w.names if a < b and len(w.presence[a] & w.presence[b]) >= 2),
                   key=lambda x: key(cfg['seed'], 'fg-s', *x))
    for a, b in pairs[:n]:
        picks.append(sorted(w.presence[a] | w.presence[b], key=w.pos.get))
    return picks


def prepare(bench_root, out, chapters=None, overrides=None, events_root=None):
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    from .story_experimental import reading_order
    cfg = {**STORY_DEFAULTS, 'window': 6, 'per_level': 2, 'items_per_pack': 8, **(overrides or {})}
    root = Path(bench_root).resolve(); roots = [root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1')]
    out = separate(out, roots + [root / 'core'])
    facts = read(Path(events_root) / 'facts.json')['facts'] if events_root else []
    available = read(roots[0] / 'manifest.json')['config']['chapters']; chosen = sorted(chapters or available)
    if not set(chosen) <= set(available): raise ValueError('Unknown chapter scope')
    rows, sizes = [], []
    for cid in chosen:
        g, v, pins = load_world(roots[0], roots[1], cid); rich = load_optional(*roots, cid, pins)
        w = World(g, v, rich); order = reading_order(str(root / 'core/v1'), cid)
        quotable = {l['text_id'] for l in w.lines(cfg)}
        events = [f for f in facts if f['chapter_id'] == cid]
        for level in LEVELS:
            for pages in choose_pages(w, level, cfg, cfg['per_level']):
                pack, idmap = build_pack(w, order, events, pages, quotable, level)
                rid = 'fg:' + stable([cid, level, pages])
                rows.append({'request_id': rid, 'chapter_id': cid, 'level': level, 'pack_pages': pages,
                             'prompt': PROMPT.format(n=cfg['items_per_pack'], pack=pack), 'idmap': idmap,
                             'snapshots': {'graph': stable(g), 'visibility': stable(v), 'rich': stable(rich)}})
                sizes.append(len(rows[-1]['prompt']))
    config = {'schema': REQUESTS, 'version': VERSION, 'chapters': chosen, 'settings': cfg, 'events_root': str(events_root) if events_root else None,
              'events_sha256': digest(Path(events_root) / 'facts.json') if events_root else None, 'code_sha256': digest(Path(__file__))}
    publish(out / 'requests.json', {'schema': REQUESTS, 'config': config, 'requests': rows})
    report = {'requests': len(rows), 'by_level': dict(Counter(r['level'] for r in rows)), 'max_prompt_chars': max(sizes) if sizes else 0,
              'approx_max_tokens': (max(sizes) // 3) if sizes else 0}
    publish(out / 'report.json', report)
    return report


def chat(endpoint, model, prompt, max_tokens, temperature, timeout=900):
    body = {'model': model, 'temperature': temperature, 'max_tokens': max_tokens, 'messages': [{'role': 'user', 'content': prompt}]}
    req = urllib.request.Request(endpoint.rstrip('/') + '/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())['choices'][0]['message']['content']


def run(requests_root, endpoint, model, out, workers=4, limit=None, max_tokens=6000, temperature=0.7, retries=3):
    requests_root = Path(requests_root).resolve(); out = separate(out, [requests_root])
    rows = read(requests_root / 'requests.json')['requests']; rows = rows[:limit] if limit else rows
    publish(out / 'config.json', {'schema': 'comics_qa.benchmark1000.freegen_responses.1', 'requests_sha256': digest(requests_root / 'requests.json'),
                                  'endpoint': endpoint, 'model': model, 'max_tokens': max_tokens, 'temperature': temperature})
    def one(r):
        path = out / 'responses' / (stable(r['request_id']) + '.json')
        if path.exists(): return 'reused'
        for attempt in range(retries):
            try:
                text = chat(endpoint, model, r['prompt'], max_tokens, temperature); break
            except Exception:
                if attempt == retries - 1: return 'failed'
                time.sleep(2 ** attempt)
        publish(path, {'request_id': r['request_id'], 'model': model, 'text': text})
        return 'answered'
    with ThreadPoolExecutor(workers) as pool:
        counts = Counter(pool.map(one, rows))
    return {'requests': len(rows), **counts}


def parse_items(text):
    """First JSON list in the response; tolerant of code fences and surrounding prose."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S)  # reasoning models (Qwen3-VL-Thinking)
    m = re.search(r'\[.*\]', text, re.S)
    if not m: return None
    try:
        value = json.loads(m.group(0))
    except ValueError:
        return None
    return value if isinstance(value, list) else None


CLAIM_RE = re.compile(r'^\s*([A-Z_]+)\s*\(\s*([^)]*)\)\s*$')


def resolve(prop, request):
    """Parse one proposed item and resolve pack IDs to graph IDs. Returns (item_core, error)."""
    if not isinstance(prop, dict) or not isinstance(prop.get('question'), str) or not isinstance(prop.get('claims'), list):
        return None, 'schema'
    fmt = prop.get('answer_format')
    if fmt not in ANSWER_FORMATS: return None, 'answer_format'
    idmap = request['idmap']

    def graph_id(short):
        short = str(short).strip()
        return idmap.get(short[:1], {}).get(short)
    claims = []
    for raw in prop['claims']:
        m = CLAIM_RE.match(str(raw))
        if not m or m.group(1) not in CLAIMS: return None, 'claim_syntax'
        args = [graph_id(x) for x in m.group(2).split(',')]
        if None in args: return None, 'unknown_id'
        claims.append({'type': m.group(1), 'args': args, 'text': str(raw)})
    ref = prop.get('answer_ref')
    if fmt == 'line_sequence':
        refs = [graph_id(x) for x in (ref if isinstance(ref, list) else [])]
        if not refs or None in refs: return None, 'answer_ref'
        answer = {'type': 'sequence', 'refs': refs}
    else:
        g = graph_id(ref) if isinstance(ref, str) else None
        if g is None or str(ref)[:1] != {'character': 'C', 'page': 'P', 'line': 'L'}[fmt]: return None, 'answer_ref'
        answer = {'type': fmt, 'ref': g}
    return {'question': prop['question'].strip(), 'answer_format': {'line_sequence': 'sequence', 'line': 'quote'}.get(fmt, fmt),
            'answer': answer, 'claims': claims}, None


def ingest(bench_root, requests_root, responses_root, out):
    """Validate every proposal; accepted items become an experimental story store."""
    import fcntl
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    from .freegen_check import Facts, check_claim, check_item, display
    from .story_families import ITEM
    root = Path(bench_root).resolve(); roots = [root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1')]
    requests_root, responses_root = Path(requests_root).resolve(), Path(responses_root).resolve()
    out = separate(out, roots + [root / 'core', requests_root, responses_root])
    doc = read(requests_root / 'requests.json'); rconf = doc['config']
    events = {f['fact_id']: f for f in read(Path(rconf['events_root']) / 'facts.json')['facts']} if rconf.get('events_root') else {}
    cfg = dict(rconf['settings'], core_root=str(root / 'core/v1'))
    reasons, kept, seen, by_level = Counter(), [], set(), Counter()
    by_chapter = defaultdict(list)
    for r in doc['requests']: by_chapter[r['chapter_id']].append(r)
    for cid, reqs in sorted(by_chapter.items()):
        g, v, pins = load_world(roots[0], roots[1], cid); rich = load_optional(*roots, cid, pins)
        snap = {'graph': stable(g), 'visibility': stable(v), 'rich': stable(rich)}
        F = Facts(g, v, rich, cfg['core_root'], events)
        split = next(n['split'] for n in g['nodes'] if n['type'] == 'Chapter')
        for r in reqs:
            path = responses_root / 'responses' / (stable(r['request_id']) + '.json')
            if not path.exists(): reasons['no_response'] += 1; continue
            if r['snapshots'] != snap: reasons['stale_request'] += 1; continue
            props = parse_items(read(path)['text'])
            if props is None: reasons['unparsable_response'] += 1; continue
            for prop in props:
                reasons['proposed'] += 1
                core, err = resolve(prop, r)
                if err: reasons[err] += 1; continue
                tiers = {check_claim(F, c)[1] for c in core['claims']}
                ans = core['answer']
                if ans['type'] == 'sequence':
                    ans['value'] = [display(F, 'L', x) for x in ans['refs']]
                    if len({F.page_of.get(x) for x in ans['refs']}) < len(ans['refs']): tiers.add('M')
                else:
                    ans['value'] = display(F, {'character': 'C', 'page': 'P', 'quote': 'L'}[core['answer_format']], ans['ref'])
                used = sorted({'M': 'magi_reading_order', 'A': 'audited_event_facts'}[t] for t in tiers if t in ('M', 'A'))
                body = {'family': 'free_generation', 'chapter_id': cid, 'question': core['question'], 'options': [], 'answer': ans}
                item = {'schema': ITEM, 'version': VERSION, 'item_id': 'story:' + stable(body), **body, 'split': split,
                        'answer_format': core['answer_format'], 'evidence_class': 'executed', 'generation_mode': 'free_generation',
                        'reasoning_structure': 'chain' if len(core['claims']) > 1 else 'direct', 'primary_group': 'short',
                        'reasoning_tags': ['free_generation', 'level_' + r['level']], 'question_form': 'free_generation',
                        'evidence': {'lines': [], 'claims': core['claims'], 'request_id': r['request_id']},
                        'pack_level': r['level'], 'pack_pages': r['pack_pages'], 'track': 'experimental', 'uses_model_facts': used,
                        'source': {'snapshots': snap},
                        'features': {'identity_id': ans.get('ref') if core['answer_format'] == 'character' else None,
                                     'two_option': False, 'semantic_target': stable(['free_generation', core['claims'], ans.get('ref') or ans.get('refs')])},
                        'complexity': {'necessary_pages': sorted({p for c in core['claims'] for p in [F.page_of.get(x) or (x if x in F.pos else None) for x in c['args']] if p},
                                                                key=F.pos.get), 'story_hops': len(core['claims']), 'meaningful_hops': None},
                        'verification': {'proof': 'claims_checked', 'human': 'required', 'release': 'pending',
                                         'flags': ['needs_human_verification', 'needs_uniqueness_check', 'free_generation', 'experimental_track']}}
                result = check_item(item, g, v, rich, cfg, events)
                if not result['verified']: reasons[result['errors'][0].split(':')[0]] += 1; continue
                if item['item_id'] in seen: reasons['duplicate'] += 1; continue
                seen.add(item['item_id']); kept.append(item); by_level[r['level']] += 1; reasons['accepted'] += 1
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.story-writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        config = {'schema': STORE, 'version': VERSION, 'settings': cfg, 'requests_sha256': digest(requests_root / 'requests.json'),
                  'responses_config_sha256': digest(responses_root / 'config.json'), 'events_root': rconf.get('events_root'),
                  'facts_root': rconf.get('events_root'), 'facts_sha256': rconf.get('events_sha256'), 'code_sha256': digest(Path(__file__))}
        if not config['facts_root']: config.pop('facts_root'); config.pop('facts_sha256')
        publish(out / 'config.json', config); outputs = {}
        for item in kept:
            name = 'candidates/' + stable(item['item_id']) + '.json'; publish(out / name, item); outputs[name] = digest(out / name)
        report = {'reasons': dict(reasons), 'accepted_by_level': dict(by_level), 'candidates': len(kept),
                  'families': {'free_generation': len(kept)}, 'rejected': reasons['proposed'] - len(kept)}
        publish(out / 'report.json', report); outputs['report.json'] = digest(out / 'report.json')
        publish(out / 'manifest.json', {'schema': STORE, 'config': config, 'config_sha256': stable(config), 'outputs_sha256': outputs,
                                        'counts': {'candidates': len(kept)}, 'release_status': 'not_approved'})
    return report
