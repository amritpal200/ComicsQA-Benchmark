"""Finite typed relay, with independently checked cross-stage bindings."""
from .io import stable
from .scan import ScanEngine, ScanChecker
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.tasks.graph.crl.language import call
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker


def syntax(program, pages):
    if set(program) not in ({'op', 'quote', 'page'}, {'op', 'quote', 'page', 'other_rule'}) or program['op'] != 'speaker_relay':
        raise ValueError('Invalid relay program')
    if program.get('other_rule', 'different') not in ('different', 'any'):
        raise ValueError('Unknown relay other-character rule')
    if not isinstance(program['quote'], str) or not program['quote'].strip():
        raise ValueError('Relay needs an exact quote')
    if type(program['page']) is not int or not 1 <= program['page'] <= len(pages):
        raise ValueError('Invalid relay anchor page')
    return program


class RelayEngine:
    def __init__(self, graph, visibility, rich):
        self.g, self.v, self.r = graph, visibility, rich

    def execute(self, program):
        syntax(program, self.g['page_ids'])
        speaker = call('speaker_char', call('quote', program['quote'], on=call('page', program['page'])))
        first_program = {'op': 'next_speaks', 'characters': [speaker], 'after': program['page']}
        first = ScanEngine(self.g, self.v, self.r).execute(first_program)
        stages = [{'engine': 'scan', 'execution': first}]
        final = first['result']
        if final['status'] == 'OK':
            middle_page = final['display']
            # Selecting a different character is essential: selecting the only
            # speaker on their next speaking page would just recover the same person.
            others = call('filter', call('chars_on', call('page', middle_page)),
                          {'lambda': {'param': 'c', 'body': call('neq', {'var': 'c'}, speaker)}})
            other_program = call('the', others if program.get('other_rule', 'different') == 'different' else call('chars_on', call('page', middle_page)))
            other = Interpreter(self.g, self.v, rich=self.r).execute(other_program)
            stages.append({'engine': 'crl', 'execution': other})
            if other['result']['status'] == 'OK':
                last_program = {'op': 'next_presence', 'characters': [other_program], 'after': middle_page}
                last = ScanEngine(self.g, self.v, self.r).execute(last_program)
                stages.append({'engine': 'scan', 'execution': last})
                final = last['result']
            else:
                final = {'status': other['result']['status'], 'value': None, 'display': None}
        return {'schema': 'comics_qa.benchmark1000.relay.1', 'program': program,
                'graph_sha256': stable(self.g), 'visibility_sha256': stable(self.v),
                'rich_sha256': stable(self.r), 'stages': stages,
                'result': final, 'release_status': 'pending_question_gates'}


class RelayChecker:
    def __init__(self, graph, visibility, rich):
        self.g, self.v, self.r = graph, visibility, rich

    def check(self, doc):
        try:
            if doc['schema'] != 'comics_qa.benchmark1000.relay.1':
                raise ValueError('Wrong relay schema')
            if (doc['graph_sha256'], doc['visibility_sha256'], doc['rich_sha256']) != (stable(self.g), stable(self.v), stable(self.r)):
                raise ValueError('Relay sources differ')
            program = syntax(doc['program'], self.g['page_ids']); stages = doc['stages']
            if not 1 <= len(stages) <= 3:
                raise ValueError('Invalid relay stage count')
            anchor = call('speaker_char', call('quote', program['quote'], on=call('page', program['page'])))
            expected_first = {'op': 'next_speaks', 'characters': [anchor], 'after': program['page']}
            a = stages[0]['execution']
            if stages[0]['engine'] != 'scan' or stable(a['program']) != stable(expected_first):
                raise ValueError('Relay initial anchor mismatch')
            first_check = ScanChecker(self.g, self.v, self.r).check(a)
            if not first_check['proof_valid']:
                raise ValueError('Invalid first relay proof')
            expected_result = a['result']; required = 1
            if a['result']['status'] == 'OK':
                required = 2
                if len(stages) < 2 or stages[1]['engine'] != 'crl':
                    raise ValueError('Missing other-character stage')
                page = a['result']['display']
                # Checker builds this binding from the verified previous output,
                # never from the page claimed by the submitted second stage.
                expected_other = call('the', call('filter', call('chars_on', call('page', page)),
                    {'lambda': {'param': 'c', 'body': call('neq', {'var': 'c'}, anchor)}}))
                if program.get('other_rule', 'different') == 'any':
                    expected_other = call('the', call('chars_on', call('page', page)))
                b = stages[1]['execution']
                checked = ProofChecker(self.g, self.v, rich=self.r).check(b, expected_other)
                if not checked['proof_valid']:
                    raise ValueError('Invalid other-character proof or page binding')
                if b['result']['status'] == 'OK':
                    required = 3
                    if len(stages) < 3 or stages[2]['engine'] != 'scan':
                        raise ValueError('Missing final relay stage')
                    c = stages[2]['execution']
                    expected_last = {'op': 'next_presence', 'characters': [expected_other], 'after': page}
                    if stable(c['program']) != stable(expected_last):
                        raise ValueError('Wrong final relay dependency')
                    checked = ScanChecker(self.g, self.v, self.r).check(c)
                    if not checked['proof_valid']:
                        raise ValueError('Invalid final scan proof')
                    expected_result = c['result']
                else:
                    expected_result = {'status': b['result']['status'], 'value': None, 'display': None}
            if len(stages) != required or stable(expected_result) != stable(doc['result']):
                raise ValueError('Extra stages or wrong relay result')
            return {'proof_valid': True, 'answer_supported': doc['result']['status'] == 'OK',
                    'status': doc['result']['status'], 'checked_stages': required}
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            return {'proof_valid': False, 'answer_supported': False, 'error': str(exc)}
