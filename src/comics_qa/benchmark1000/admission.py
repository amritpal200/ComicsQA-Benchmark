"""Fresh native question admission, separate from original answer-proof receipts."""
import copy
import re
from collections import OrderedDict
from comics_qa.tasks.graph.gen2.quality import normalized, form_is_visible, usable_name
from comics_qa.tasks.graph.generation.gates import without_pages
from comics_qa.evidence.graph.rich.model import build
from .io import stable
from .native import check_answer
from .native_wording import parse_question, bound, speaker
from .semantic import execute, support, atomic_executions

VERSION = 'native_admission.1'
VISUAL = {'present', 'speaks_on', 'spoken_by', 'on_page', 'is_char'}


def name_eligibility(g, v, cid, form, reviews=()):
    node = next((n for n in g['nodes'] if n['id'] == cid and n['type'] == 'Character'), None)
    if not node or node['generic']:
        return 'name_generic_or_unknown'
    if not form_is_visible(v, cid, form):
        return 'name_unreadable'
    if not usable_name(g, v, cid, form, reviews):
        return 'name_alias_unapproved'
    owners = {n['id'] for n in g['nodes'] if n['type'] == 'Character' and not n['generic']
              and normalized(form) in {normalized(f) for f in [n['canonical_name'], *n['aliases']]}}
    return None if owners == {cid} else 'name_ambiguous'


class World:
    def __init__(self, g, v, r):
        self.g, self.v, self.r = g, v, r
        self.cache = OrderedDict()

    def changed(self, pages, text_only=False):
        key = (tuple(pages), text_only)
        if key not in self.cache:
            g, v = without_pages(self.g, self.v, pages, text_only)
            if text_only:
                # Match the frozen RichGates OCR-only definition, including locations.
                nodes = {n['id']: n for n in self.g['nodes']}
                ids = {f['fact_id'] for f in g['facts']}
                for f in self.g['facts']:
                    if (f['rel'] in ('named', 'alias') or f['rel'] == 'on_page' and nodes[f['args'][0]]['type'] == 'Text') and f['fact_id'] not in ids:
                        g['facts'].append(copy.deepcopy(f))
                original = {(c['page_id'], c['family']): c for c in self.g['coverage']}
                g['coverage'] = [copy.deepcopy(original[c['page_id'], c['family']]) if c['family'] == 'text_boxes' else c for c in g['coverage']]
            else:
                v['alignments'] = [a for a in v['alignments'] if a['page_id'] not in pages]
            self.cache[key] = (g, v, build(g, v, self.r['sources'], ()))
            if len(self.cache) > 8:
                self.cache.popitem(last=False)
        return self.cache[key]

    def run(self, engine, program, world=None):
        doc, check, supported = execute(engine, program, *(world or (self.g, self.v, self.r)))
        return {'result': doc['result'], 'proof_valid': check['proof_valid'], 'answer_supported': bool(supported),
                'execution_sha256': stable(doc), 'execution': doc}


def same_answer(result, original):
    return result['status'] == 'OK' and result.get('exact', True) and result['value'] == original['value']


def resolved_path(item, parsed, world, evidence=None):
    """Resolve identity operands; never deduplicate by quote strings or answer alone."""
    def char(ast):
        row = world.run('crl', ast)
        if evidence is not None:
            evidence.append(row)
        if not row['answer_supported'] or row['result']['status'] != 'OK':
            raise ValueError('Unproved resolved character operand')
        return row['result']['value']
    if 'profile_version' in parsed:
        from .complexity import resolved
        return resolved(item, parsed)
    p = parsed['program']; target = item['execution']['result']['value']
    prefix = [item['chapter_id'], parsed['kind']]
    if parsed['kind'] == 'three_page_clue':
        return prefix + [sorted(parsed['clue_keys']), target]
    if parsed['kind'] == 'speaker_relay':
        stages = item['execution']['stages']
        return prefix + [p['page'], char(speaker(p['quote'], p['page'])),
                         stages[0]['execution']['result']['value'], stages[1]['execution']['result']['value'], target]
    return prefix + [p['after'], sorted(char(ast) for ast in p['characters']), target]


def assess(item, world, reviews=(), max_ablation_pages=8):
    """Fail closed; persisted proposal complexity and necessity claims are not inputs."""
    if type(max_ablation_pages) is not int or max_ablation_pages < 1:
        raise ValueError('Positive admission page budget required')
    g, v, r = world.g, world.v, world.r
    receipt = {'version': VERSION, 'proposal_id': item['item_id'], 'proposal_sha256': stable(item),
               'snapshots': item['source']['snapshots'], 'reasons': [], 'checks': {}, 'passed': False}
    reasons, checks = receipt['reasons'], receipt['checks']
    checks['answer'] = check_answer(item, g, v, r)
    if not checks['answer']['answer_supported']:
        reasons.append('answer_unproved'); return receipt
    if item['answer_format'] not in ('page', 'character', 'count', 'boolean', 'set', 'sequence') or item['generation_mode'] != 'template' or item['evidence_class'] != 'executed':
        reasons.append('unsupported_admission_profile'); return receipt
    if r is None or r['decisions']:
        reasons.append('unsupported_rich_counterfactuals'); return receipt
    try:
        parsed = parse_question(item['question'])
    except ValueError as error:
        checks['wording'] = {'pass': False, 'detail': str(error)}
        reasons.append('wording_unrecognized'); return receipt
    checks['wording'] = {'pass': bound(parsed, item), 'kind': parsed['kind'], 'method': 'independent_closed_template_parse'}
    if not checks['wording']['pass']:
        reasons.append('wording_program_mismatch'); return receipt
    if item['answer_format'] == 'sequence' and parsed.get('kind') != 'branch_chain_pages':
        reasons.append('unsupported_sequence_admission_profile'); return receipt
    original = item['execution']['result']
    if 'unrestricted' in parsed:
        unrestricted = world.run('crl', parsed['unrestricted'])
        checks['wording']['unrestricted_domain'] = unrestricted
        if not unrestricted['answer_supported'] or not same_answer(unrestricted['result'], original):
            reasons.append('wording_hidden_named_domain')
    # Exact answer forms and names embedded in literal quoted text follow GEN-2 policy.
    refs = set()
    if item['answer_format'] == 'character':
        refs.add((item['answer']['identity_id'], item['answer']['value']))
    question = ' ' + normalized(item['question']) + ' '
    for node in g['nodes']:
        if node['type'] == 'Character' and not node['generic']:
            for form in [node['canonical_name'], *[a['form'] for a in reviews if a['identity_id'] == node['id']]]:
                if normalized(form) and ' ' + normalized(form) + ' ' in question:
                    refs.add((node['id'], form))
    checks['names'] = [{'identity_id': cid, 'form': form, 'reason': name_eligibility(g, v, cid, form, reviews)} for cid, form in sorted(refs)]
    reasons.extend(row['reason'] for row in checks['names'] if row['reason'])
    checks['alias_reviews'] = list(reviews)
    answer_text = str(item['answer']['value'])
    leaked = (bool(re.search(r'(?<!\w)' + re.escape(answer_text) + r'(?!\w)', item['question']))
              if item['answer_format'] in ('page', 'count') else ' ' + normalized(answer_text) + ' ' in question)
    checks['answer_leakage'] = {'pass': not leaked}
    if leaked:
        reasons.append('answer_in_question')
    used = set(item['evidence']['fact_ids'])
    transcripts = {t['id']: t for t in r['transcripts']}
    from comics_qa.evidence.graph.rich.model import normalize
    disagreements = []
    for f in r['facts']:
        if f['id'] in used and f['rel'] == 'transcript':
            t = transcripts[f['premises'][0]]
            if not normalize(t['paddle_text']) == normalize(t['magi_text']) == t['consensus']:
                disagreements.append(t['id'])
    checks['transcript_agreement'] = {'pass': not disagreements, 'disagreements': disagreements}
    if disagreements:
        reasons.append('transcript_disagreement')
    checks['clause_removals'] = []
    for removal_index, (engine, program) in enumerate(parsed['relaxations']):
        row = world.run(engine, program)
        result = row['result']
        # Known ambiguity/emptiness or a different known answer certifies necessity.
        necessary = result['status'] in (('OK', 'EMPTY') if parsed.get('allow_ambiguous_relaxations') is False else ('OK', 'AMBIGUOUS', 'EMPTY')) and not same_answer(result, original)
        if not necessary and parsed.get('alternative_relaxations'):
            trial = {**row, 'engine': engine, 'program': program}
            alt_engine, alt_program = parsed['alternative_relaxations'][removal_index]
            alternative = world.run(alt_engine, alt_program)
            row = {**alternative, 'sensitivity_trials': [trial]}; engine, program = alt_engine, alt_program
            result = row['result']
            necessary = result['status'] in ('OK', 'EMPTY') and not same_answer(result, original)
        if parsed['kind'].startswith('shared_') and 'profile_version' in parsed:
            extras = sorted(set(result['value']) - set(original['value'])) if result['status'] == 'OK' and isinstance(result['value'], list) else []
            necessary = bool(extras)
            row['known_extra_members'] = extras
        checks['clause_removals'].append({**row, 'engine': engine, 'program': program, 'necessary': necessary})
        if not necessary:
            reasons.append('clause_necessity_unknown' if result['status'] == 'UNKNOWN' else 'redundant_clause')
    checks['relay_identity_alternative'] = None
    if parsed['kind'] == 'speaker_relay':
        # An ambiguous intermediate selection alone does not establish that switching
        # identity affects the final page. Follow the original person as well.
        p = parsed['program']
        middle = item['execution']['stages'][0]['execution']['result']['display']
        alternative = {'op': 'next_presence', 'characters': [speaker(p['quote'], p['page'])], 'after': middle}
        alt = world.run('scan', alternative)
        checks['relay_identity_alternative'] = {**alt, 'program': alternative}
        if same_answer(alt['result'], original):
            reasons.append('relay_identity_switch_redundant')
        elif alt['result']['status'] not in ('OK', 'EMPTY'):
            reasons.append('relay_identity_necessity_unknown')
    evidence = support(item['proof_engine'], item['execution'], g, r)
    checks['page_removals'] = []
    if len(evidence['pages']) > max_ablation_pages:
        reasons.append('page_ablation_budget_exceeded')
    else:
        for pid in evidence['pages']:
            row = world.run(item['proof_engine'], item['program'], world.changed([pid]))
            checks['page_removals'].append({**row, 'removed_page': pid, 'necessary': not same_answer(row['result'], original)})
    necessary_pages = [row['removed_page'] for row in checks['page_removals'] if row['necessary']]
    visual_pages = {p for f in g['facts'] if f['fact_id'] in used and f['rel'] in VISUAL for p in f['page_ids']}
    needed_visual = [p for p in necessary_pages if p in visual_pages]
    checks['necessary_pages'] = necessary_pages
    checks['necessary_visual_pages'] = needed_visual
    if len(needed_visual) < parsed['min_pages']:
        reasons.append('insufficient_necessary_visual_pages')
    text_only = world.run(item['proof_engine'], item['program'], world.changed(g['page_ids'], True))
    checks['text_only'] = text_only
    if same_answer(text_only['result'], original):
        reasons.append('text_only_solves')
    if 'profile_version' in parsed:
        from .complexity import bindings, certify
        values = bindings(item)
        checks['resolved_bindings'] = values
        if len(parsed['recipe']['references']) == 2 and values['c0']['value'] == values['c1']['value']:
            reasons.append('branches_resolve_same_identity')
        if parsed['kind'].startswith('shared_'):
            result = original['value']; domain = parsed['recipe']['end'] - parsed['recipe']['start'] + 1
            if not isinstance(result, list) or not 2 <= len(result) < domain:
                reasons.append('trivial_or_singleton_page_set')
        if parsed['kind'] == 'speaking_gap' and original['value'] < 1:
            reasons.append('trivial_zero_gap')
        if parsed['kind'] in ('speaking_gap', 'speaking_before') and values['pa']['value'] == values['pb']['value']:
            reasons.append('coincident_branch_targets')
        if parsed.get('profile_version') == 'branch_relations.1':
            ends = [values[f'p{b}_{parsed["recipe"]["steps"][b]-1}']['value'] for b in range(2)]
            if ends[0] == ends[1]: reasons.append('coincident_branch_targets')
            if parsed['kind'] == 'branch_chain_gap' and original['value'] < 1: reasons.append('trivial_zero_gap')
            if parsed['kind'] == 'branch_chain_pages' and len(original['value']) != 2: reasons.append('non_distinct_page_sequence')
        receipt['complexity_certificate'] = certify(item, parsed, checks)
        if not receipt['complexity_certificate']['certified']:
            reasons.append('complexity_uncertified')
    receipt['resolved_characters'] = []
    receipt['resolved_path'] = resolved_path(item, parsed, world, receipt['resolved_characters'])
    receipt['resolved_path_sha256'] = stable(receipt['resolved_path'])
    receipt['kind'] = parsed['kind']
    receipt['reasons'] = sorted(set(reasons))
    receipt['passed'] = not receipt['reasons']
    return receipt


def deduplicate(items, receipts):
    """Choose only among passing proposals; preserve all hold/duplicate provenance."""
    representatives = {}
    decisions = {}
    for item in sorted(items, key=lambda i: (len(i['question'].split()), i['item_id'])):
        row = receipts[item['item_id']]
        if not row['passed']:
            decisions[item['item_id']] = {'status': 'held', 'reasons': row['reasons']}
            continue
        key = row['resolved_path_sha256']
        if key in representatives:
            decisions[item['item_id']] = {'status': 'duplicate', 'duplicate_of': representatives[key], 'reasons': ['duplicate_resolved_path']}
        else:
            representatives[key] = item['item_id']
            decisions[item['item_id']] = {'status': 'admitted', 'reasons': []}
    return decisions
