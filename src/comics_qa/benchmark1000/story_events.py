"""Event question families (improvement plan S6) from audited, independently confirmed event facts (S5).

- event_actor_choice: 'On the page where someone says "<quote>", which named character <event>?' with four named options.
  Distractors are named characters not drawn on that page (closed human character/name coverage), so the gold is
  unique whenever the confirmed fact is true.
- event_order: four confirmed events on four different pages; answer their chapter order (human page order).

Facts are used only through a passed audit (record_audit). The quote locator reuses the story-family lines
(distinctiveness certificate). Items are story_item.1 records in a story_store.1 and are checked by story_check.
"""
import fcntl
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from .io import digest, publish, read, separate, stable, verify_manifest
from .story_families import DEFAULTS as STORY_DEFAULTS, LETTERS, STORE, World, key, make, names_in

VERSION = 'story_events.1'
AUDIT = 'comics_qa.benchmark1000.event_audit.1'
SUBJECT = 'the outlined character'
DEFAULTS = dict(STORY_DEFAULTS, per_family=8, max_audit_errors=3)


def question_clause(statement):
    """'In the foreground, the outlined character ... grips a fork.' -> 'in the foreground, which named character ... grips a fork'."""
    text = statement.strip().rstrip('.!')
    i = text.lower().index(SUBJECT)
    text = text[:i] + 'which named character' + text[i + len(SUBJECT):]
    return text[0].lower() + text[1:]


def moment(statement):
    """Event description for ordering options, without the outline reference."""
    text = statement.strip()
    i = text.lower().index(SUBJECT)
    text = text[:i] + 'someone' + text[i + len(SUBJECT):]
    return text[0].upper() + text[1:]


def record_audit(facts_root, decisions_path, out, max_errors=3):
    """Validate one decision (correct/wrong) for every audit fact; pass if wrong <= max_errors."""
    facts_root = Path(facts_root).resolve(); out = separate(out, [facts_root])
    report = read(facts_root / 'report.json'); decisions = read(decisions_path)
    rows = decisions.get('decisions', decisions) if isinstance(decisions, dict) else decisions
    by_id = {}
    for d in rows:
        fid, verdict = d.get('fact_id'), d.get('verdict')
        if verdict not in ('correct', 'wrong'): raise ValueError('Verdict must be correct or wrong: ' + str(fid))
        if fid in by_id: raise ValueError('Duplicate decision: ' + fid)
        by_id[fid] = d
    expected = report['audit_ids']
    short = {f[6:18]: f for f in expected}
    by_id = {short.get(k, k): v for k, v in by_id.items()}  # accept the 12-character IDs shown on audit.html
    if set(by_id) != set(expected): raise ValueError(f'Decisions must cover exactly the {len(expected)} audit facts')
    if not all(isinstance(by_id[f].get('reviewer'), str) and by_id[f]['reviewer'].strip() for f in expected):
        raise ValueError('Every decision needs a reviewer name')
    wrong = sorted(f for f in expected if by_id[f]['verdict'] == 'wrong')
    result = {'schema': AUDIT, 'facts_report_sha256': digest(facts_root / 'report.json'), 'facts_sha256': digest(facts_root / 'facts.json'),
              'audited': len(expected), 'wrong': len(wrong), 'wrong_ids': wrong, 'max_errors': max_errors,
              'status': 'passed' if len(wrong) <= max_errors else 'failed',
              'decisions': [{'fact_id': f, **{k: by_id[f][k] for k in ('verdict', 'reviewer') if k in by_id[f]},
                             'note': by_id[f].get('note', '')} for f in expected]}
    publish(out / 'audit.json', result)
    return {k: result[k] for k in ('audited', 'wrong', 'status', 'max_errors')}


def usable_facts(facts_root, audit_root):
    facts_root = Path(facts_root).resolve(); audit = read(Path(audit_root) / 'audit.json')
    if audit.get('schema') != AUDIT or audit['status'] != 'passed': raise ValueError('Event facts need a passed audit')
    if audit['facts_sha256'] != digest(facts_root / 'facts.json'): raise ValueError('Audit is for different event facts')
    wrong = set(audit['wrong_ids'])
    return [f for f in read(facts_root / 'facts.json')['facts'] if f['fact_id'] not in wrong], audit


def event_actor_choice(w, lines, facts, cfg):
    items, used, per_identity = [], set(), Counter()
    by_page = defaultdict(list)
    for line in lines: by_page[line['page_id']].append(line)
    for f in sorted(facts, key=lambda x: (x['identity_id'] in w.frequent, key(cfg['seed'], 'eac', x['fact_id']))):
        if len(items) >= cfg['per_family']: break
        s, page = f['identity_id'], f['page_id']
        if s not in w.names or per_identity[s] >= cfg['per_answer_identity'] or not w.closed(page, ('char_boxes', 'names')): continue
        anchors = [l for l in sorted(by_page[page], key=lambda l: key(cfg['seed'], f['fact_id'], l['text_id'])) if l['text_id'] not in used]
        if not anchors: continue
        line = anchors[0]
        drawn = w.identified(page)
        pool = sorted((c for c in w.names if c not in drawn and w.names[c] != w.names[s]),
                      key=lambda c: (c not in w.speaks, key(cfg['seed'], f['fact_id'], c)))
        chosen, shown = [], {w.names[s]}
        for c in pool:
            if w.names[c] not in shown: chosen.append(c); shown.add(w.names[c])
            if len(chosen) == 3: break
        if len(chosen) < 3 or names_in(line['quote'] + ' ' + f['statement'], [x for c in [s] + chosen for x in w.forms(c)]): continue
        order = sorted(chosen, key=lambda c: key(cfg['seed'], 'eac-order', f['fact_id'], c)); order.insert(len(items) % 4, s)
        options = [{'letter': LETTERS[i], 'identity_id': c, 'text': w.names[c]} for i, c in enumerate(order)]
        question = ('On the page where someone says "' + line['quote'] + '", ' + question_clause(f['statement']) + '? Choose one: '
                    + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.')
        evidence = {'lines': [line], 'events': [f], 'absent_options': order[:len(items) % 4] + order[len(items) % 4 + 1:],
                    'coverage': [w.coverage[(page, x)]['coverage_id'] for x in ('char_boxes', 'names')],
                    'option_visibility': {c: w.vis[c]['verified_evidence_ids'] for c in order}}
        items.append(make(w, 'event_actor_choice', question, options, {'type': 'choice', 'value': LETTERS[order.index(s)], 'identity_id': s,
                          'display': w.names[s]}, 'multiple_choice', 'chain', evidence, [page], 2, s))
        used.add(line['text_id']); per_identity[s] += 1
    return items


def event_order(w, facts, cfg):
    items, used = [], set()
    rng = random.Random(key(cfg['seed'], 'eo', w.g['chapter_id']))
    by_page = defaultdict(list)
    for f in sorted(facts, key=lambda x: key(cfg['seed'], 'eo-fact', x['fact_id'])): by_page[f['page_id']].append(f)
    pages = sorted(by_page, key=w.pos.get)
    for _ in range(cfg['per_family'] * 20):
        if len(items) >= cfg['per_family']: break
        free = [p for p in pages if any(f['fact_id'] not in used for f in by_page[p])]
        if len(free) < 4: break
        picked = [next(f for f in by_page[p] if f['fact_id'] not in used) for p in sorted(rng.sample(free, 4), key=w.pos.get)]
        if len({f['identity_id'] for f in picked}) < 2: continue
        shown = sorted(picked, key=lambda f: key(cfg['seed'], 'eo-show', f['fact_id']))
        if shown == picked: shown = picked[1:] + picked[:1]
        options = [{'letter': LETTERS[i], 'fact_id': f['fact_id'], 'text': moment(f['statement'])} for i, f in enumerate(shown)]
        question = ('Put these moments in the order they happen in the chapter, first to last: '
                    + ' '.join(o['letter'] + ') ' + o['text'] for o in options) + ' Answer with the four letters.')
        items.append(make(w, 'event_order', question, options, {'type': 'sequence', 'value': [LETTERS[shown.index(f)] for f in picked]},
                          'sequence', 'compare', {'lines': [], 'events': picked}, [f['page_id'] for f in picked], 4, None))
        used.update(f['fact_id'] for f in picked)
    return items


def chapter(g, v, rich, facts, cfg):
    from .story_check import check
    w = World(g, v, rich); lines = w.lines(cfg)
    items = event_actor_choice(w, lines, facts, cfg) + event_order(w, facts, cfg)
    for item in items:
        # Event facts are model output (captions + independent verifier); until a human audit, every item says so.
        item['verification'] = {**item['verification'], 'human': 'required',
                                'flags': ['needs_human_verification', 'event_fact_' + cfg['audit_basis'] + '_audited']}
    for item in items:  # event items are identified by their facts as well as their lines
        item['features']['semantic_target'] = stable([item['family'], sorted(e['fact_id'] for e in item['evidence']['events']),
                                                      sorted(l['text_id'] for l in item['evidence']['lines'])])
    kept, rejected = [], []
    for item in items:
        r = check(item, g, v, rich, cfg, events={f['fact_id']: f for f in facts})
        (kept if r['verified'] else rejected).append(item if r['verified'] else {'item_id': item['item_id'], 'errors': r['errors']})
    return {'chapter_id': g['chapter_id'], 'eligible_lines': len(lines), 'facts': len(facts), 'items': kept, 'rejected': rejected,
            'counts': dict(Counter(i['family'] for i in kept))}


def run(bench_root, facts_root, audit_root, out, chapters=None, overrides=None):
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    cfg = dict(DEFAULTS, **(overrides or {}))
    root = Path(bench_root).resolve(); roots = [root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1')]
    facts, audit = usable_facts(facts_root, audit_root)
    if audit['wrong'] > cfg['max_audit_errors']: raise ValueError('Audit error count above the configured limit')
    reviewers = {d.get('reviewer', '') for d in audit['decisions']}
    cfg['audit_basis'] = 'ai' if all('claude' in r or r.endswith('_ai') or '_ai_' in r for r in reviewers) else 'human'
    out = separate(out, roots + [root / 'core', Path(facts_root), Path(audit_root)])
    by_chapter = defaultdict(list)
    for f in facts: by_chapter[f['chapter_id']].append(f)
    chosen = sorted(chapters or by_chapter)
    config = {'schema': STORE, 'version': VERSION, 'chapters': chosen, 'settings': cfg,
              'facts_root': str(Path(facts_root).resolve()), 'facts_sha256': digest(Path(facts_root) / 'facts.json'), 'audit_sha256': digest(Path(audit_root) / 'audit.json'),
              'source_manifests_sha256': {str(p): digest(p / 'manifest.json') for p in roots},
              'code_sha256': {p.name: digest(p) for p in Path(__file__).parent.glob('story_*.py')}}
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.story-writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish(out / 'config.json', config)
        outputs, report = {}, {'chapters': {}, 'families': Counter(), 'rejected': 0, 'audit': {k: audit[k] for k in ('audited', 'wrong', 'status')}}
        for cid in chosen:
            path = out / 'chapters' / (cid + '.json')
            if path.exists():
                saved = read(path)
                if saved['config_sha256'] != stable(config): raise ValueError('Stale event checkpoint')
                result = saved['payload']
            else:
                g, v, pins = load_world(roots[0], roots[1], cid); rich = load_optional(*roots, cid, pins)
                result = chapter(g, v, rich, by_chapter[cid], cfg)
                publish(path, {'config_sha256': stable(config), 'payload': result})
            outputs[str(path.relative_to(out))] = digest(path)
            for item in result['items']:
                name = 'candidates/' + stable(item['item_id']) + '.json'; publish(out / name, item); outputs[name] = digest(out / name)
            report['chapters'][cid] = {'facts': result['facts'], **result['counts'], 'rejected': len(result['rejected'])}
            report['families'].update(result['counts']); report['rejected'] += len(result['rejected'])
        report['families'] = dict(report['families']); report['candidates'] = sum(report['families'].values())
        publish(out / 'report.json', report); outputs['report.json'] = digest(out / 'report.json')
        publish(out / 'manifest.json', {'schema': STORE, 'config': config, 'config_sha256': stable(config), 'outputs_sha256': outputs,
                                        'counts': {'candidates': report['candidates']}, 'release_status': 'not_approved'})
    return report
