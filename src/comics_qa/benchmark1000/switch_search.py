"""Bounded, independently checked dependency preselection; never admission."""
from collections import Counter
from .expanded_families import compile_recipe, parse_question, render
from .semantic import execute
from .admission import same_answer
from .io import stable

VERSION = 'necessary_switches.1'


class DependencyBudget(Exception):
    pass


class Dependencies:
    def __init__(self, g, v, rich, limit=128):
        if type(limit) is not int or limit < 1:
            raise ValueError('Positive dependency execution budget required')
        self.g, self.v, self.rich = g, v, rich
        self.limit = limit; self.used = 0; self.cache_hits = 0; self.cache = {}
        self.counts = Counter(); self.records = []; self.exhausted = False

    def query(self, engine, program):
        key = stable([engine, program])
        if key in self.cache:
            self.cache_hits += 1
            return self.cache[key]
        if self.used >= self.limit:
            self.exhausted = True
            raise DependencyBudget()
        self.used += 1
        doc, checked, supported = execute(engine, program, self.g, self.v, self.rich)
        if not checked['proof_valid']:
            raise ValueError('Dependency producer/checker disagreement')
        row = {'engine': engine, 'program_sha256': stable(program), 'execution_sha256': stable(doc),
               'proof_valid': True, 'answer_supported': bool(supported), 'result': doc['result']}
        self.cache[key] = row
        return row

    def assess(self, recipe):
        if recipe['kind'] != 'speaker_walk':
            raise ValueError('Dependency preselection requires a character-switch recipe')
        parsed = parse_question(render(recipe))
        record = {'recipe': recipe, 'interventions': [], 'passed': False}
        self.records.append(record)
        try:
            main = self.query(parsed['engine'], compile_recipe(recipe)); record['main'] = main
            if not main['answer_supported']:
                reason = 'main_answer_unproved'
            else:
                reason = 'passed'
                # Test identity changes first to avoid spending navigation work on
                # a walk already known to work without switching characters.
                trials = list(zip(parsed['relaxation_labels'], parsed['relaxations']))
                trials.sort(key=lambda x: (not x[0].startswith('switch:'), x[0]))
                for label, (engine, program) in trials:
                    row = self.query(engine, program)
                    result = row['result']
                    if same_answer(result, main['result']): outcome = 'redundant'
                    elif result['status'] == 'EMPTY' or result['status'] == 'OK' and row['answer_supported']: outcome = 'necessary'
                    else: outcome = 'unproved'
                    record['interventions'].append({'label': label, 'outcome': outcome, **row})
                    if outcome != 'necessary':
                        reason = 'redundant_' + label.split(':')[0] if outcome == 'redundant' else 'unproved_' + label.split(':')[0]
                        break
            record['passed'] = reason == 'passed'; record['reason'] = reason
        except DependencyBudget:
            record['reason'] = 'dependency_budget_exhausted'
            record['unchecked_interventions'] = len(parsed['relaxations']) - len(record['interventions'])
            self.counts[record['reason']] += 1
            raise
        self.counts[record['reason']] += 1
        record['unchecked_interventions'] = len(parsed['relaxations']) - len(record['interventions'])
        return record

    def report(self):
        return {'version': VERSION, 'scope': 'per_chapter', 'execution_limit': self.limit,
                'new_executions': self.used, 'cache_hits': self.cache_hits, 'budget_exhausted': self.exhausted,
                'outcomes': dict(self.counts), 'candidates_checked': len(self.records), 'records': self.records,
                'authority': 'discovery_only; first blocking intervention; full admission remains mandatory'}
