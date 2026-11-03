"""Story-level profile of candidates (improvement plan S2): content category, anchor, wording, unit dependence.

Read-only view: records are never changed. Rules are deterministic and based on saved family, schema,
structure and question text, so a profile can be recomputed at selection time.
"""
import re
from collections import Counter
from pathlib import Path
from .io import digest, publish, read, separate, stable, verify_manifest
from .pool import ADMITTED, LEGACY, PAIRED

SCHEMA = 'comics_qa.benchmark1000.story_profile.1'
TARGETS = 'benchmark1000.story_targets.1'
CATEGORIES = ('dialogue', 'character', 'event', 'story_order', 'multi_hop', 'contrast', 'perception')
ANCHORS = ('quote', 'character', 'event', 'relative', 'page')

# Legacy GEN-1/GEN-2 families: (content_category, unit_dependence).
LEGACY_FAMILIES = {
    'count_texts': ('perception', 'box_count'),
    'count_apps': ('perception', 'box_count'),
    'line_count': ('perception', 'box_count'),
    'compare_text_count': ('perception', 'box_count'),
    'quote_speaker_depictions': ('perception', 'box_count'),
    'name_speaker_depictions': ('perception', 'box_count'),
    'next_appearance': ('character', 'page_presence'),
    'character_constraints': ('character', 'page_presence'),
    'quote_speaker_next_page': ('character', 'page_presence'),
    'quote_speaker': ('dialogue', 'none'),
    'name_speaker': ('dialogue', 'none'),
    'single_speaker': ('dialogue', 'none'),
}
STORY = 'comics_qa.benchmark1000.story_item.1'
STORY_FAMILIES = {'quote_speaker_choice': ('dialogue', 'none'), 'quote_speaker_open': ('dialogue', 'none'),
                  'quote_order': ('story_order', 'none'), 'conversation_partner': ('character', 'page_presence'),
                  'next_speech_partner': ('multi_hop', 'page_presence'), 'shared_character': ('multi_hop', 'page_presence'),
                  'event_actor_choice': ('event', 'page_presence'), 'event_order': ('event', 'none')}
BOX_WORDS = re.compile(r'text regions?|depictions?', re.I)
PRESENCE_WORDS = re.compile(r'\bdrawn\b|\bappears?\b|\bshown\b', re.I)
PROCEDURAL = re.compile(r'search only|use only pages|start immediately before|condition one|'
                        r'each new search starts|inclusive range', re.I)
PAGE_REFERENCE = re.compile(r'\bpages? \d+', re.I)
QUOTED = re.compile(r'"[^"]*"')
RELATIVE = re.compile(r'\b(after|before) [^.?]*\b(first|last|next)\b', re.I)


def union_key(item):
    """Pool key; contrast members are unwrapped to the native path they share with admitted items."""
    from .pool import key
    if item['schema'] == STORY:
        return ['story', item['chapter_id'], item['source']['snapshots'], item['features']['semantic_target'], item.get('contrast')]
    if item['schema'] == PAIRED:
        return ['native_path', item['chapter_id'], item['source']['snapshots'], item['admission_receipt']['resolved_path_sha256']]
    return key(item)


def family(item):
    return item['legacy'].get('family') if item['schema'] == LEGACY else None


def page_answer(item):
    value = item['answer'].get('value')
    if item['answer_format'] == 'page': return True
    return item['answer_format'] in ('set', 'sequence') and isinstance(value, list) and all(isinstance(v, int) for v in value)


def anchor(item, question):
    if item['schema'] == STORY and item['family'] == 'event_order': return 'event'
    canonical = item['legacy'].get('canonical', '') if item['schema'] == LEGACY else ''
    if '"' in question or 'name form' in question: return 'quote'
    if RELATIVE.search(question): return 'relative'
    if '(char "' in canonical: return 'character'
    return 'page'


def profile(item):
    question = item['question']
    procedural = bool(PROCEDURAL.search(question))
    if item['schema'] == STORY:
        category, unit = STORY_FAMILIES[item['family']]
        if 'contrast' in item: category = 'contrast'
    elif item['schema'] == LEGACY:
        category, unit = LEGACY_FAMILIES.get(family(item), (None, None))
        if category is None: raise ValueError('Unprofiled legacy family: ' + str(family(item)))
    elif item['schema'] in (ADMITTED, PAIRED):
        unit = 'box_count' if BOX_WORDS.search(question) else 'page_presence' if PRESENCE_WORDS.search(question) else 'none'
        if item['schema'] == PAIRED: category = 'contrast'
        elif unit == 'box_count': category = 'perception'
        elif item['reasoning_structure'] in ('chain', 'branch_combine') or item.get('primary_group') in ('chain', 'long_relational'):
            category = 'multi_hop'
        elif 'speak' in question.lower(): category = 'dialogue'
        else: category = 'character'
    else:
        raise ValueError('Unknown candidate schema: ' + item['schema'])
    complexity = item.get('complexity') or {}
    hops = complexity.get('story_hops') if item['schema'] == STORY else complexity.get('meaningful_hops')
    return {'content_category': category, 'anchor_type': anchor(item, question),
            'wording_style': 'procedural' if procedural else 'natural', 'unit_dependence': unit,
            'page_reference': bool(PAGE_REFERENCE.search(QUOTED.sub('', question))), 'page_answer': page_answer(item),
            'count_answer': item['answer_format'] == 'count', 'story_hops': hops if isinstance(hops, int) else None,
            'words': len(question.split()),
            'human_required': (item.get('verification') or {}).get('human') == 'required'}


def check_targets(targets):
    if targets.get('version') != TARGETS: raise ValueError('Unknown story target version')
    if set(targets['categories']) != set(CATEGORIES): raise ValueError('Targets must name every content category')
    if sum(targets['categories'].values()) != targets['total']: raise ValueError('Category targets must sum to total')
    return targets


def summarize(profiles, targets):
    """Supply per field and per category; available = natural wording (procedural only up to its cap)."""
    targets = check_targets(targets); n = len(profiles)
    def count(field): return dict(sorted(Counter(str(p[field]) for p in profiles).items()))
    flags = {'box_count': lambda p: p['unit_dependence'] == 'box_count', 'count_answer': lambda p: p['count_answer'],
             'perception': lambda p: p['content_category'] == 'perception', 'procedural': lambda p: p['wording_style'] == 'procedural',
             'page_reference': lambda p: p['page_reference'], 'page_answer': lambda p: p['page_answer']}
    shares = {k: {'candidates': sum(map(f, profiles)), 'share': round(sum(map(f, profiles)) / n, 4) if n else None,
                  'final_max_items': int(targets['max_share'][k] * targets['total'])} for k, f in flags.items()}
    categories = {}
    for c, want in targets['categories'].items():
        mine = [p for p in profiles if p['content_category'] == c]
        natural = sum(p['wording_style'] == 'natural' for p in mine)
        story = sum(p['wording_style'] == 'natural' and not p['page_reference'] for p in mine)
        categories[c] = {'target': want, 'candidates': len(mine), 'natural_wording': natural,
                         'natural_without_page_number': story, 'shortfall_natural': max(0, want - natural)}
    hops = targets['min_multi_hop_story_hops']
    deep = sum(p['content_category'] == 'multi_hop' and (p['story_hops'] or 0) >= hops for p in profiles)
    return {'candidates': n, 'content_category': count('content_category'), 'anchor_type': count('anchor_type'),
            'wording_style': count('wording_style'), 'unit_dependence': count('unit_dependence'),
            'caps': shares, 'categories': categories, 'multi_hop_with_certified_min_hops': deep,
            'total_shortfall_natural': sum(v['shortfall_natural'] for v in categories.values()),
            'needs_human_verification': sum(bool(p.get('human_required')) for p in profiles)}


def markdown(report):
    s = report['summary']
    lines = ['# Story profile of the candidate pool', '',
             f"Candidates: {s['candidates']} (distinct under pool keys; contrast members unwrapped). Read-only view; no record changed.", '',
             '| Category | Target | Candidates | Natural wording | Natural, no page number | Shortfall (natural) |',
             '|---|---:|---:|---:|---:|---:|']
    lines += [f"| {c} | {v['target']} | {v['candidates']} | {v['natural_wording']} | {v['natural_without_page_number']} | {v['shortfall_natural']} |"
              for c, v in s['categories'].items()]
    lines += ['', f"Total natural-wording shortfall: {s['total_shortfall_natural']}. "
              f"Multi-hop items with certified ≥{report['targets']['min_multi_hop_story_hops']} hops: {s['multi_hop_with_certified_min_hops']}. "
              f"Flagged `needs_human_verification`: {s.get('needs_human_verification', 0)}.", '',
              '| Cap | Candidates | Share of pool | Max items in final 1,000 |', '|---|---:|---:|---:|']
    lines += [f"| {k} | {v['candidates']} | {v['share']:.1%} | {v['final_max_items']} |" for k, v in s['caps'].items()]
    for field in ('anchor_type', 'wording_style', 'unit_dependence'):
        lines += ['', f'{field}: ' + ', '.join(f'{k} {v}' for k, v in s[field].items())]
    return '\n'.join(lines) + '\n'


def run(stores, targets_path, out):
    from .store import load
    out = separate(out, list(stores) + [targets_path]); targets = check_targets(read(targets_path))
    seen = {}; occurrences = 0
    for root in stores:
        for item in load(root):
            occurrences += 1; k = stable(union_key(item))
            # A path that is also a contrast-pair member is profiled as that member.
            if k not in seen or (item['schema'] == PAIRED and seen[k]['schema'] != PAIRED): seen[k] = item
    profiles = {k: {'item_id': i['item_id'], 'chapter_id': i['chapter_id'], 'split': i.get('split'), **profile(i)}
                for k, i in sorted(seen.items())}
    config = {'stores': [{'path': str(Path(r).resolve()), 'manifest_sha256': digest(Path(r) / 'manifest.json')} for r in stores],
              'targets': targets, 'targets_sha256': stable(targets),
              'code_sha256': digest(Path(__file__)), 'occurrences': occurrences}
    report = {'schema': SCHEMA, 'config': config, 'targets': targets, 'summary': summarize(list(profiles.values()), targets),
              'release_status': 'not_approved'}
    publish(out / 'profiles.json', {'schema': SCHEMA, 'profiles': profiles})
    publish(out / 'report.json', report)
    (out / 'report.md').exists() or (out / 'report.md').write_text(markdown(report))
    if (out / 'report.md').read_text() != markdown(report): raise ValueError('Existing report.md differs; choose a new output')
    names = ('profiles.json', 'report.json', 'report.md')
    publish(out / 'manifest.json', {'schema': SCHEMA, 'config_sha256': stable(config),
                                    'outputs_sha256': {n: digest(out / n) for n in names}, 'counts': {'candidates': len(profiles)}})
    return report


def load_profiles(root):
    m = verify_manifest(root)
    if m.get('schema') != SCHEMA: raise ValueError('Not a story profile output')
    return read(Path(root) / 'profiles.json')['profiles']
