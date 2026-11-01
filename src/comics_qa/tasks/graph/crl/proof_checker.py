"""Strict CRL-1 trace verification using checker-owned semantic rules.

No call to the producer interpreter. Diagnostic prose (`reason`) is not a proof
claim; values, statuses, exactness, bindings, topology and all support are checked.
"""
from dataclasses import replace
import json

try:
    from .language import VERSION, SPECS, bind, canonical, element, infer, parse, program_hash
    from .proof_rules import CLOSED, SUPPORT, TRUST, World, Checked, boolean, combine, encoded, normalized, unknown
except ImportError:
    from language import VERSION, SPECS, bind, canonical, element, infer, parse, program_hash
    from proof_rules import CLOSED, SUPPORT, TRUST, World, Checked, boolean, combine, encoded, normalized, unknown

CHECKER_VERSION = 'crl2.1'


class InvalidProof(ValueError):
    def __init__(self, path, message):
        self.path = path
        super().__init__(message)


def require(condition, path, message):
    if not condition: raise InvalidProof(path, message)


def equal(actual, expected, path):
    # Python equates True and 1. Proof JSON must preserve these distinct types.
    require(encoded(actual) == encoded(expected), path, 'Claim differs from independently computed value')


class ProofChecker:
    def __init__(self, graph, visibility, max_steps=50000, allow_closed_assumed=True, rich=None):
        if type(max_steps) is not int or max_steps < 1: raise ValueError('Invalid checker step budget')
        self.closed = CLOSED if allow_closed_assumed else CLOSED - {'closed_assumed'}
        self.world = World(graph, visibility, self.closed, rich)
        self.max_steps = max_steps

    def trust(self, support):
        w = self.world
        origins = [w.facts[f]['origin'] for f in support['facts']]
        origins += [w.nodes[n]['origin'] for n in support['node_refs']]
        origins += [w.evidence[e]['origin'] for e in support['visibility_evidence']]
        return min(origins, key=TRUST.get) if origins else None

    def record(self, expression, computed, children=()):
        index = self.cursor
        require(index < self.limit, 'proof.steps', 'Checker step budget exceeded')
        require(index < len(self.steps), 'proof.steps', 'Missing proof step')
        step = self.steps[index]
        path = f'proof.steps[{index}]'
        require(isinstance(step, dict), path, 'Expected a step object')
        expected = {'nid': index, 'expression': canonical(expression),
                    'op': expression.get('op', 'let' if 'let' in expression else 'var' if 'var' in expression else 'literal') if isinstance(expression, dict) else 'literal',
                    'type': computed.type, 'value': computed.value, 'status': computed.status,
                    'exact': computed.exact, 'ordered': computed.ordered,
                    'children': [c.nid for c in children if c.nid >= 0],
                    'trust_min': self.trust(computed.support)}
        expected.update({name: sorted(computed.support[name], key=self.world.index.get) if name == 'range_pages'
                         else sorted(computed.support[name]) for name in SUPPORT})
        require(set(step) == set(expected) | {'reason'}, path, 'Missing/extra step fields')
        require(isinstance(step['reason'], str), path + '.reason', 'Expected diagnostic string')
        for name, value in expected.items(): equal(step[name], value, path + '.' + name)
        self.cursor += 1
        self.used_facts.update(computed.support['facts'])
        if expected['op'] in ('char', 'name_texts') and computed.status != 'OK': self.names_ok = False
        return replace(computed, nid=index)

    def walk(self, expression, environment=None):
        environment = {} if environment is None else environment
        require(self.cursor < self.limit, 'proof.steps', 'Checker step budget exceeded')
        if type(expression) in (int, bool, str):
            return self.record(expression, Checked(value=expression, type=infer(expression)))
        if 'enum' in expression:
            return self.record(expression, Checked(value=expression['enum'], type='Cmp'))
        if 'var' in expression:
            source = environment[expression['var']]
            return self.record(expression, source, [source])
        if 'let' in expression:
            local, children = dict(environment), []
            for binding in expression['let']:
                result = self.walk(binding['value'], local)
                local[binding['name']] = result
                children.append(result)
            result = self.walk(expression['in'], local)
            return self.record(expression, result, children + [result])
        arguments = bind(expression)
        op = expression['op']
        values, children = {}, []
        for name, argument in arguments.items():
            if name == 'fn': continue
            if name == 'values':
                values[name] = [self.walk(x, environment) for x in argument]
                children.extend(values[name])
            else:
                values[name] = self.walk(argument, environment)
                children.append(values[name])
        if op in ('and', 'or'):
            result = boolean(op, values['values'])
        elif any(c.status != 'OK' for c in children):
            first = next(c for c in children if c.status != 'OK')
            result = combine(inputs=children, status=first.status, exact=False)
        elif op in ('quote', 'name_texts') and self.world.rich_hash is not None:
            result = self.world.rich_query(op, values)
        elif SPECS[op]['deferred']:
            result = unknown(children)
        elif arguments.get('fn') is not None:
            lam = arguments['fn']['lambda']
            sequence = values['S']
            outputs = []
            for member in sequence.value:
                binding = combine(member, [sequence], exact=True)
                binding.type = element(sequence.type)
                outputs.append(self.walk(lam['body'], {**environment, lam['param']: binding}))
            children.extend(outputs)
            result = self.world.functional(op, values, outputs)
        else:
            result = self.world.operation(op, values)
        result.type = infer(expression, {k: v.type for k, v in environment.items()})
        return self.record(expression, result, children)

    def premise_closure(self, ids):
        result, pending = set(), list(ids)
        while pending:
            fid = pending.pop()
            if fid not in result:
                result.add(fid)
                pending.extend(self.world.facts[fid]['premises'])
        return result

    def check_derivations(self, ids):
        """Check supported CKG rules, not merely that their premise IDs exist."""
        w = self.world
        for fid in self.premise_closure(ids):
            fact = w.facts[fid]
            if fact['derivation'] != 'R': continue
            rel, args = fact['rel'], fact['args']
            premises = [w.facts[p] for p in fact['premises']]
            def has(relation, arguments):
                return any(p['rel'] == relation and p['args'] == arguments for p in premises)
            valid = False
            if rel == 'is_char':
                valid = w.nodes[args[0]].get('identity_id') == args[1] and has('on_page', [args[0], w.page(args[0])])
            elif rel == 'alias':
                valid = args[1] in w.nodes[args[0]]['aliases'] and has('named', [args[0], w.nodes[args[0]]['canonical_name']])
            elif rel == 'present':
                valid = any(p['rel'] == 'is_char' and p['args'][1] == args[0]
                            and has('on_page', [p['args'][0], args[1]]) for p in premises)
            elif rel == 'is_line':
                valid = any(p['rel'] == 'spoken_by' and p['args'][0] == args[0] for p in premises)
            elif rel == 'speaks_on':
                valid = any(p['rel'] == 'spoken_by' and has('is_char', [p['args'][1], args[0]])
                            and has('on_page', [p['args'][0], args[1]]) and has('on_page', [p['args'][1], args[1]]) for p in premises)
            elif rel == 'co_present':
                valid = has('present', [args[0], args[2]]) and has('present', [args[1], args[2]])
            require(valid and fact['rule_id'] == rel + ':' + w.graph['builder_version'],
                    'graph.facts.' + fid, 'Derived relation does not follow from its stated premises')

    def final_claims(self, document, expression, result):
        w = self.world
        facts = self.premise_closure(result.support['facts'])
        visibility = set(result.support['visibility_evidence'])
        answer_visibility = set()
        display = result.value
        if result.status == 'OK' and result.type in ('Char', 'Set[Char]', 'Seq[Char]'):
            names = []
            for cid in [result.value] if result.type == 'Char' else result.value:
                entry = w.visibility[cid]
                forms = entry['verified_forms']
                if w.nodes[cid]['generic'] or not forms:
                    self.names_ok = False
                    names.append(None)
                    continue
                name = entry['canonical_name'] if entry['canonical_visible'] else min(forms, key=lambda f: (len(f), f))
                names.append(name)
                eid = next(e for e in entry['verified_evidence_ids'] if w.evidence[e]['normalized_form'] == normalized(name))
                answer_visibility.add(eid)
            display = names[0] if result.type == 'Char' else names
        if result.status == 'OK' and result.type in ('Page', 'Span', 'Seq[Page]', 'Set[Page]'):
            positions = [w.index[p]+1 for p in ([result.value] if result.type == 'Page' else result.value)]
            display = positions[0] if result.type == 'Page' else positions
        visibility.update(answer_visibility)
        renderable = result.type in ('Bool3', 'Int', 'Cmp', 'Page', 'Char', 'Span', 'Seq[Page]', 'Set[Page]', 'Seq[Char]', 'Set[Char]')
        lower_bound = isinstance(expression, dict) and expression.get('op') == 'at_least' and result.value is True
        eligible = bool(result.status == 'OK' and renderable and self.names_ok and (result.exact or lower_bound))
        claimed = document['result']
        for k, value in dict(value=result.value, type=result.type, display=display, status=result.status, exact=result.exact).items():
            equal(claimed[k], value, 'result.' + k)
        require(isinstance(claimed.get('reason'), str), 'result.reason', 'Expected diagnostic string')
        equal(document['eligible_for_generation'], eligible, 'eligible_for_generation')
        support = {**result.support, 'facts': facts, 'visibility_evidence': visibility}
        positive_pages = {p for f in facts for p in w.facts[f]['page_ids']}
        positive_pages.update(w.evidence[e]['page_id'] for e in visibility)
        expected = {'root': result.nid, 'facts': sorted(facts),
                    'certificates': sorted(result.support['certificates']), 'visibility_evidence': sorted(visibility),
                    'answer_visibility_evidence': sorted(answer_visibility), 'node_refs': sorted(result.support['node_refs']),
                    'range_pages': sorted(result.support['range_pages'], key=w.index.get),
                    'key_support_pages': sorted(positive_pages, key=w.index.get), 'trust_min': self.trust(support)}
        require(set(document['proof']) == set(expected) | {'steps'}, 'proof', 'Missing/extra proof fields')
        for name, value in expected.items(): equal(document['proof'][name], value, 'proof.' + name)
        return eligible

    def check(self, document, expected_program=None):
        """Return a fresh report; never modify the submitted result or graph.

        expected_program optionally binds the result to a caller-specified query.
        ERROR results are rejected: interrupted/invalid execution is not a proof.
        """
        self.cursor = 0
        self.names_ok = True
        self.used_facts = set()
        report = {'schema': 'comics_qa.crl_check.v1', 'checker_version': CHECKER_VERSION,
                  'chapter_id': self.world.graph['chapter_id'], 'status': 'REJECTED',
                  'proof_valid': False, 'accepted_for_generation': False, 'checked_steps': 0, 'errors': []}
        try:
            equal(document.get('rich_evidence_sha256'), self.world.rich_hash, 'rich_evidence_sha256')
            require(document['schema'] == 'comics_qa.crl_result.v1' and document['crl_version'] == VERSION,
                    'schema', 'Unsupported result schema or language version')
            equal(document['chapter_id'], self.world.graph['chapter_id'], 'chapter_id')
            require(document['result']['status'] != 'ERROR', 'result.status', 'ERROR/unfinished executions are not checkable proofs')
            expression = parse(document['program'])
            infer(expression)
            equal(document['canonical'], canonical(expression), 'canonical')
            equal(document['program_sha256'], program_hash(expression), 'program_sha256')
            if expected_program is not None:
                equal(program_hash(expression), program_hash(parse(expected_program)), 'expected_program')
            expression = parse(canonical(expression), 'sexpr')
            policy = document['policy']
            equal(policy['closed_statuses'], sorted(self.closed), 'policy.closed_statuses')
            equal(policy['page_indexing'], '1-based full supplied chapter', 'policy.page_indexing')
            equal(policy['nonexact_final'], 'rejected except top-level at_least true', 'policy.nonexact_final')
            require(type(policy['max_steps']) is int and 0 < policy['max_steps'] <= self.max_steps,
                    'policy.max_steps', 'Producer budget exceeds checker policy or is invalid')
            self.limit = policy['max_steps']
            self.steps = document['proof']['steps']
            require(isinstance(self.steps, list) and 0 < len(self.steps) <= self.limit,
                    'proof.steps', 'Empty, oversized, or malformed trace')
            result = self.walk(expression)
            equal(self.cursor, len(self.steps), 'proof.steps')
            self.check_derivations(self.used_facts)
            accepted = self.final_claims(document, expression, result)
            report.update(status='VERIFIED', proof_valid=True, accepted_for_generation=accepted,
                          program_sha256=program_hash(expression), result_status=result.status,
                          result_exact=result.exact, result_value=result.value)
        except InvalidProof as exc:
            report['errors'].append({'path': exc.path, 'message': str(exc)})
        except (ValueError, KeyError, TypeError, IndexError, RecursionError, AttributeError, OverflowError) as exc:
            report['errors'].append({'path': 'document', 'message': 'Malformed/unsupported proof: ' + str(exc)})
        report['checked_steps'] = self.cursor
        return report
