"""New-layer minimal-prefix page navigation, verified through independent CRL probes.

No legacy operation registry changes. Later open pages do not invalidate a proved
first witness, while any unknown earlier page blocks a 'next' claim.
"""
from .io import stable
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.tasks.graph.crl.language import call, infer
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker

OPS = {'next_presence': (1, 'present'), 'next_speaks': (1, 'speaks_on'), 'next_joint': (2, 'present'), 'last_presence': (1, 'present')}


def syntax(program, pages):
    if set(program) not in ({'op', 'characters', 'after'}, {'op', 'characters', 'after', 'end'}) or program['op'] not in OPS:
        raise ValueError('Invalid scan program')
    arity = OPS[program['op']][0]
    if len(program['characters']) != arity or any(infer(c) != 'Char' for c in program['characters']):
        raise ValueError('Scan character input type mismatch')
    after = program['after']
    if type(after) is not int or not 0 <= after <= len(pages):
        raise ValueError('Invalid scan anchor')
    if program['op'] == 'last_presence' and after != 0:
        raise ValueError('Last presence uses the whole chapter; after must be 0')
    end = program.get('end', len(pages))
    if type(end) is not int or not after <= end <= len(pages) or program['op'] == 'last_presence' and 'end' in program:
        raise ValueError('Invalid bounded scan end')
    return program


class ScanEngine:
    def __init__(self, graph, visibility, rich=None):
        self.g, self.v, self.rich = graph, visibility, rich
        closed = {'closed_assumed', 'closed_verified', 'closed_audited'}
        order = {c['page_id']: c['status'] for c in graph['coverage'] if c['family'] == 'page_sequence'}
        if any(order.get(p) not in closed for p in graph['page_ids']):
            raise ValueError('Scan needs admitted chapter page order')

    def execute(self, program):
        syntax(program, self.g['page_ids'])
        engine = Interpreter(self.g, self.v, rich=self.rich)
        indexes = list(range(program['after'] + 1, program.get('end', len(self.g['page_ids'])) + 1))
        if program['op'] == 'last_presence':
            indexes.reverse()
        probes = []; value = None; status = 'EMPTY'
        relation = OPS[program['op']][1]
        for number in indexes:
            args = [call(relation, c, call('page', number)) for c in program['characters']]
            expression = args[0] if len(args) == 1 else call('and', *args)
            doc = engine.execute(expression)
            probes.append({'page_number': number, 'execution': doc})
            r = doc['result']
            if r['status'] != 'OK' or type(r['value']) is not bool:
                status = 'UNKNOWN'; break
            if r['value']:
                status = 'OK'; value = self.g['page_ids'][number - 1]; break
        return {'schema': 'comics_qa.benchmark1000.scan.1', 'program': program,
                'graph_sha256': stable(self.g), 'visibility_sha256': stable(self.v),
                'rich_sha256': stable(self.rich), 'probes': probes,
                'result': {'status': status, 'value': value,
                           'display': self.g['page_ids'].index(value) + 1 if value else None},
                'release_status': 'pending_question_gates'}


class ScanChecker:
    def __init__(self, graph, visibility, rich=None):
        self.g, self.v, self.rich = graph, visibility, rich

    def check(self, document):
        try:
            if document['schema'] != 'comics_qa.benchmark1000.scan.1':
                raise ValueError('Wrong scan schema')
            if (document['graph_sha256'], document['visibility_sha256'], document['rich_sha256']) != (stable(self.g), stable(self.v), stable(self.rich)):
                raise ValueError('Scan source mismatch')
            program = syntax(document['program'], self.g['page_ids'])
            closed = {'closed_assumed', 'closed_verified', 'closed_audited'}
            sequence = [c for c in self.g['coverage'] if c['family'] == 'page_sequence']
            if {c['page_id'] for c in sequence if c['status'] in closed} != set(self.g['page_ids']):
                raise ValueError('Unverified page sequence')
            numbers = list(range(program['after'] + 1, program.get('end', len(self.g['page_ids'])) + 1))
            if program['op'] == 'last_presence':
                numbers = sorted(numbers, reverse=True)
            probes = document['probes']
            checker = ProofChecker(self.g, self.v, rich=self.rich)
            terminal = None; value = None
            for at, probe in enumerate(probes):
                if terminal is not None or at >= len(numbers) or probe['page_number'] != numbers[at]:
                    raise ValueError('Skipped, reordered or extra scan probe')
                relation = 'speaks_on' if program['op'] == 'next_speaks' else 'present'
                predicates = [call(relation, c, call('page', numbers[at])) for c in program['characters']]
                expected = predicates[0] if len(predicates) == 1 else call('and', *predicates)
                checked = checker.check(probe['execution'], expected)
                if not checked['proof_valid']:
                    raise ValueError('Invalid independent probe proof')
                r = probe['execution']['result']
                if r['status'] != 'OK' or type(r['value']) is not bool:
                    terminal = 'UNKNOWN'
                elif r['value'] is True:
                    terminal = 'OK'; value = self.g['page_ids'][numbers[at] - 1]
            if terminal is None:
                if len(probes) != len(numbers):
                    raise ValueError('Missing negative prefix/suffix evidence')
                terminal = 'EMPTY'
            expected = {'status': terminal, 'value': value,
                        'display': self.g['page_ids'].index(value) + 1 if value else None}
            if stable(expected) != stable(document['result']):
                raise ValueError('Incorrect scan result')
            return {'proof_valid': True, 'answer_supported': terminal == 'OK',
                    'checked_pages': len(probes), 'status': terminal}
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            return {'proof_valid': False, 'answer_supported': False, 'error': str(exc)}
