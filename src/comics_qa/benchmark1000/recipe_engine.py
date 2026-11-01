"""Typed let recipes: checked CRL atoms plus bounded first-witness scans.

The checker reconstructs every cross-stage substitution and scan boundary. It
never invokes RecipeEngine and never accepts a cached producer verdict.
"""
import copy
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.tasks.graph.crl.language import bind, call, infer, parse, program_hash
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from .scan import ScanEngine, ScanChecker
from .io import stable

SCHEMA = 'comics_qa.benchmark1000.recipe_execution.1'


def substitute(node, environment, shadow=()):
    if not isinstance(node, dict):
        return node
    if 'var' in node:
        return copy.deepcopy(environment[node['var']]) if node['var'] in environment and node['var'] not in shadow else dict(node)
    if 'lambda' in node:
        p = node['lambda']['param']
        return {'lambda': {'param': p, 'body': substitute(node['lambda']['body'], environment, (*shadow, p))}}
    return {k: [substitute(v, environment, shadow) for v in value] if isinstance(value, list)
            else substitute(value, environment, shadow) if isinstance(value, dict) else value for k, value in node.items()}


def dependencies(program):
    def refs(x):
        if isinstance(x, dict):
            return {x['var']} if 'var' in x else set().union(*(refs(v) for v in x.values()))
        return set().union(*(refs(v) for v in x)) if isinstance(x, list) else set()
    needed = refs(program['in'])
    for b in reversed(program['let']):
        if b['name'] in needed:
            needed.update(refs(b['value']))
    return needed


def syntax(program):
    program = parse(program)
    infer(program)
    if set(program) != {'let', 'in'} or len(program['let']) > 12:
        raise ValueError('Recipe requires a bounded typed let graph')
    return program


def lower_scan(expression):
    if not isinstance(expression, dict) or expression.get('op') != 'first':
        return None
    seq = bind(expression)['S']
    if not isinstance(seq, dict) or seq.get('op') != 'pages_speaking':
        return None
    args = bind(seq); span = args['span']
    if not isinstance(span, dict) or span.get('op') != 'span_after':
        return None
    span = bind(span); within = span['within']
    if within.get('op') != 'pages' or span['x'].get('op') != 'page':
        return None
    a, b = bind(within), bind(span['x'])
    return {'op': 'next_speaks', 'characters': [args['c']], 'after': max(b['i'], a['i'] - 1), 'end': a['j']}


def result(stage):
    raw = stage['execution']['result']
    if stage['engine'] in ('crl', 'membership'):
        return raw
    return {'type': 'Page', **raw, 'exact': raw['status'] == 'OK', 'reason': ''}


def blocked(program, name, value):
    return {'type': infer(program), 'status': value['status'] if value['status'] != 'OK' else 'UNKNOWN', 'value': None, 'display': None,
            'exact': False, 'reason': 'Binding ' + name + ': ' + (value['status'] if value['status'] != 'OK' else 'INEXACT')}


def expression_for(expression, value, pages):
    # Source character/set expressions retain their closed evidence-backed AST.
    return call('page', pages.index(value['value']) + 1) if value['type'] == 'Page' else expression


class RecipeEngine:
    def __init__(self, g, v, rich, membership_refinement=False):
        self.g, self.v, self.rich = g, v, rich
        self.membership_refinement = membership_refinement

    def execute(self, program):
        program = syntax(program); env = {}; stages = []; final = None
        for b in program['let']:
            if b['name'] not in dependencies(program):
                continue
            expr = substitute(b['value'], env); scan = lower_scan(expr)
            engine = 'scan' if scan else 'crl'
            doc = ScanEngine(self.g, self.v, self.rich).execute(scan) if scan else Interpreter(self.g, self.v, rich=self.rich).execute(expr)
            stage = {'name': b['name'], 'engine': engine, 'execution': doc}; stages.append(stage)
            value = result(stage)
            if value['status'] != 'OK' or not value.get('exact', False):
                final = blocked(program, b['name'], value); break
            env[b['name']] = expression_for(expr, value, self.g['page_ids'])
        if final is None:
            expr = substitute(program['in'], env)
            from .membership import plan, MembershipEngine
            member = self.membership_refinement and plan(expr, self.g) is not None
            doc = MembershipEngine(self.g, self.v, self.rich).execute(expr) if member else Interpreter(self.g, self.v, rich=self.rich).execute(expr)
            stages.append({'name': '__result__', 'engine': 'membership' if member else 'crl', 'execution': doc}); final = doc['result']
        document = {'schema': SCHEMA, 'program': program, 'graph_sha256': stable(self.g), 'visibility_sha256': stable(self.v),
                'rich_sha256': stable(self.rich), 'stages': stages, 'result': final}
        if self.membership_refinement: document['membership_refinement'] = True
        return document


class RecipeChecker:
    def __init__(self, g, v, rich, membership_refinement=False):
        self.g, self.v, self.rich = g, v, rich
        self.membership_refinement = membership_refinement

    def check(self, document, expected_program=None):
        try:
            if document['schema'] != SCHEMA or (document['graph_sha256'], document['visibility_sha256'], document['rich_sha256']) != (stable(self.g), stable(self.v), stable(self.rich)):
                raise ValueError('Recipe source/schema mismatch')
            if document.get('membership_refinement', False) != self.membership_refinement:
                raise ValueError('Recipe refinement mode mismatch')
            program = syntax(document['program'])
            if expected_program is not None and program_hash(program) != program_hash(parse(expected_program)):
                raise ValueError('Recipe program binding mismatch')
            env = {}; at = 0; terminal = None
            checker = ProofChecker(self.g, self.v, rich=self.rich)
            for b in program['let']:
                if b['name'] not in dependencies(program):
                    continue
                stage = document['stages'][at]; at += 1
                if stage['name'] != b['name']:
                    raise ValueError('Missing/reordered recipe binding')
                expr = substitute(b['value'], env)
                # Independently reconstruct first(pages_speaking(..., span_after)).
                expected_scan = None
                if isinstance(expr, dict) and expr.get('op') == 'first':
                    seq = bind(expr)['S']
                    if isinstance(seq, dict) and seq.get('op') == 'pages_speaking':
                        args = bind(seq); span = args['span']
                        if isinstance(span, dict) and span.get('op') == 'span_after':
                            span = bind(span)
                            if span['within'].get('op') == 'pages' and span['x'].get('op') == 'page':
                                bounds = bind(span['within']); after = bind(span['x'])['i']
                                expected_scan = {'op': 'next_speaks', 'characters': [args['c']], 'after': max(bounds['i'] - 1, after), 'end': bounds['j']}
                if expected_scan is not None:
                    if stage['engine'] != 'scan' or stage['execution']['program'] != expected_scan or not ScanChecker(self.g, self.v, self.rich).check(stage['execution'])['proof_valid']:
                        raise ValueError('Invalid recipe bounded scan/binding')
                    raw = stage['execution']['result']
                    value = {'type': 'Page', **raw, 'exact': raw['status'] == 'OK', 'reason': ''}
                else:
                    if stage['engine'] != 'crl' or not checker.check(stage['execution'], expr)['proof_valid']:
                        raise ValueError('Invalid recipe CRL binding')
                    value = stage['execution']['result']
                if value['status'] != 'OK' or not value.get('exact', False):
                    terminal = {'type': infer(program), 'status': value['status'] if value['status'] != 'OK' else 'UNKNOWN', 'value': None, 'display': None,
                                'exact': False, 'reason': 'Binding ' + b['name'] + ': ' + (value['status'] if value['status'] != 'OK' else 'INEXACT')}
                    break
                env[b['name']] = call('page', self.g['page_ids'].index(value['value']) + 1) if value['type'] == 'Page' else expr
            if terminal is None:
                stage = document['stages'][at]; at += 1
                from .membership import plan, MembershipChecker
                final_expression = substitute(program['in'], env)
                member = self.membership_refinement and plan(final_expression, self.g) is not None
                valid = (MembershipChecker(self.g, self.v, self.rich).check(stage['execution'], final_expression)['proof_valid'] if member
                         else checker.check(stage['execution'], final_expression)['proof_valid'])
                if stage['name'] != '__result__' or stage['engine'] != ('membership' if member else 'crl') or not valid:
                    raise ValueError('Recipe final result binding mismatch')
                terminal = stage['execution']['result']
            if at != len(document['stages']) or terminal != document['result']:
                raise ValueError('Incorrect recipe result or surplus stages')
            return {'proof_valid': True, 'answer_supported': terminal['status'] == 'OK' and terminal.get('exact') is True,
                    'status': terminal['status'], 'checked_stages': at}
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            return {'proof_valid': False, 'answer_supported': False, 'error': str(error)}
