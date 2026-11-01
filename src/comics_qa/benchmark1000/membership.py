"""Complete pointwise membership and bounded last-witness proofs for new profiles."""
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.tasks.graph.crl.language import bind, call, infer, parse, program_hash
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from .io import stable
from .recipe_engine import substitute

SCHEMA = 'comics_qa.benchmark1000.membership.1'
CLOSED = {'closed_assumed', 'closed_verified', 'closed_audited'}


def known_truth(result):
    # Same three-valued truth contract used by the independent prefix scanner.
    # exact=False on a verified positive describes open collection coverage,
    # not a contradiction of the positive witness.
    return result['status'] == 'OK' and result.get('type') == 'Bool3' and type(result['value']) is bool


def plan(expression, graph):
    expression = parse(expression); mode = None
    if expression.get('op') == 'intersect':
        args = bind(expression)
        left, right = args['A'], args['B']
        if left.get('op') == 'pages' and right.get('op') == 'filter': left, right = right, left
        if left.get('op') != 'filter' or right.get('op') != 'pages': return None
        selected = bind(left); fn = selected['fn']
        if selected['S'].get('op') != 'pages' or program_hash(selected['S']) != program_hash(right) or 'lambda' not in fn: return None
        span = right; predicate = fn['lambda']['body']; variable = fn['lambda']['param']; mode = 'all'
    elif expression.get('op') == 'last':
        seq = bind(expression)['S']
        if seq.get('op') != 'pages_with': return None
        args = bind(seq); span = args['span']
        if span.get('op') != 'pages': return None
        variable = '__membership_page__'; predicate = call('present', args['c'], {'var': variable}); mode = 'last'
    else: return None
    if infer(predicate, {variable: 'Page'}) != 'Bool3': raise ValueError('Membership predicate type mismatch')
    bounds = bind(span); start, end = bounds['i'], bounds['j']
    if any(type(x) is not int for x in (start, end)) or not 1 <= start <= end <= len(graph['page_ids']):
        raise ValueError('Membership range outside chapter')
    if {c['page_id'] for c in graph['coverage'] if c['family'] == 'page_sequence' and c['status'] in CLOSED} != set(graph['page_ids']):
        raise ValueError('Membership needs admitted page order')
    return mode, start, end, variable, predicate


def answer(mode, values, unknown, graph):
    if mode == 'all':
        pages = sorted(values) # Set[Page] follows canonical entity-ID order.
        return {'type': 'Set[Page]', 'status': 'OK', 'value': pages,
                'display': [graph['page_ids'].index(p) + 1 for p in pages], 'exact': not unknown,
                'reason': 'Unresolved page membership' if unknown else ''}
    value = values[0] if values else None
    return {'type': 'Page', 'status': 'UNKNOWN' if unknown else 'OK' if value else 'EMPTY', 'value': value,
            'display': graph['page_ids'].index(value) + 1 if value else None, 'exact': bool(value) and not unknown,
            'reason': 'Unresolved last-witness suffix' if unknown else ''}


class MembershipEngine:
    def __init__(self, g, v, rich): self.g, self.v, self.rich = g, v, rich

    def execute(self, expression):
        spec = plan(expression, self.g)
        if spec is None: raise ValueError('Unsupported membership expression')
        mode, start, end, variable, predicate = spec
        numbers = list(range(start, end + 1))
        if mode == 'last': numbers.reverse()
        engine = Interpreter(self.g, self.v, rich=self.rich); probes = []; values = []; unknown = False
        for number in numbers:
            doc = engine.execute(substitute(predicate, {variable: call('page', number)}))
            probes.append({'page_number': number, 'execution': doc}); result = doc['result']
            if not known_truth(result):
                unknown = True
                if mode == 'last': break
            elif result['value']:
                values.append(self.g['page_ids'][number - 1])
                if mode == 'last': break
        return {'schema': SCHEMA, 'program': parse(expression), 'graph_sha256': stable(self.g),
                'visibility_sha256': stable(self.v), 'rich_sha256': stable(self.rich), 'probes': probes,
                'result': answer(mode, values, unknown, self.g)}


class MembershipChecker:
    def __init__(self, g, v, rich): self.g, self.v, self.rich = g, v, rich

    def check(self, doc, expected_program=None):
        try:
            if doc['schema'] != SCHEMA or (doc['graph_sha256'], doc['visibility_sha256'], doc['rich_sha256']) != (stable(self.g), stable(self.v), stable(self.rich)):
                raise ValueError('Membership source/schema mismatch')
            if expected_program is not None and program_hash(parse(expected_program)) != program_hash(parse(doc['program'])):
                raise ValueError('Membership program mismatch')
            spec = plan(doc['program'], self.g)
            if spec is None: raise ValueError('Unsupported membership proof')
            mode, start, end, variable, predicate = spec
            numbers = list(range(start, end + 1)) if mode == 'all' else list(range(end, start - 1, -1))
            checker = ProofChecker(self.g, self.v, rich=self.rich); values = []; uncertain = False; stopped = False
            for at, probe in enumerate(doc['probes']):
                if stopped or at >= len(numbers) or probe['page_number'] != numbers[at]: raise ValueError('Missing/reordered/extra membership probe')
                expected = substitute(predicate, {variable: call('page', numbers[at])})
                if not checker.check(probe['execution'], expected)['proof_valid']: raise ValueError('Invalid membership predicate proof')
                result = probe['execution']['result']
                settled = result['status'] == 'OK' and result.get('type') == 'Bool3' and type(result['value']) is bool
                if not settled:
                    uncertain = True; stopped = mode == 'last'
                elif result['value'] is True:
                    values.append(self.g['page_ids'][numbers[at] - 1]); stopped = mode == 'last'
            if not stopped and len(doc['probes']) != len(numbers): raise ValueError('Missing membership domain/suffix coverage')
            if mode == 'all':
                values = sorted(values)
                expected = {'type': 'Set[Page]', 'status': 'OK', 'value': values,
                            'display': [self.g['page_ids'].index(p) + 1 for p in values], 'exact': not uncertain,
                            'reason': 'Unresolved page membership' if uncertain else ''}
            else:
                value = values[0] if values else None
                expected = {'type': 'Page', 'status': 'UNKNOWN' if uncertain else 'OK' if value else 'EMPTY', 'value': value,
                    'display': self.g['page_ids'].index(value) + 1 if value else None, 'exact': bool(value) and not uncertain,
                    'reason': 'Unresolved last-witness suffix' if uncertain else ''}
            if expected != doc['result']: raise ValueError('Incorrect membership result/exactness')
            return {'proof_valid': True, 'answer_supported': expected['status'] == 'OK' and expected['exact'], 'status': expected['status']}
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            return {'proof_valid': False, 'answer_supported': False, 'error': str(error)}
