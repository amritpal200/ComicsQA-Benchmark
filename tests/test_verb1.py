"""CPU-only VERB-1 grammar, provenance, portability and resume checks."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from comics_qa.tasks.graph.verbalization import prepare as p
from comics_qa.tasks.graph.verbalization.gloss import parse_gloss
from comics_qa.tasks.graph.crl.language import call, canonical, program_hash


def item():
    ast = call('count', call('texts', call('page', 2)))
    key = program_hash(ast)
    execution = {'program': ast, 'canonical': canonical(ast), 'program_sha256': key,
                 'chapter_id': 'chapter', 'eligible_for_generation': True,
                 'inputs_sha256': {}, 'result': {'status': 'OK', 'value': 8, 'display': 8}}
    return {'item_id': 'q:one', 'chapter_id': 'chapter', 'question': 'How many text regions are shown on page 2?',
            'program': ast, 'canonical': canonical(ast), 'program_sha256': key,
            'answer': {'type': 'int', 'value': 8}, 'context': {'page_indexing': '1-based'},
            'family': 'count_texts', 'execution': execution,
            'proof_check': {'program_sha256': key, 'chapter_id': 'chapter', 'result_value': 8,
                            'execution_sha256': p.stable(execution), 'proof_valid': True,
                            'accepted_for_generation': True}}


class GlossTests(unittest.TestCase):
    def test_templates(self):
        cases = [
            ('How many character depictions are shown on page 2?', 'count'),
            ('How many text regions are shown on page 2?', 'count'),
            ('How many text regions on page 4 have Son Goku as their speaker?', 'line_count'),
            ('Who is the speaker of the only dialogue text region on page 3?', 'speaker_char'),
            ('After L appears on page 2, on which later page is this character next drawn?', 'page_of'),
            ('Is Mr. A drawn on page 7?', 'at_least'),
            ('Compared with page 9, does page 2 contain more text regions, fewer, or the same number?', 'compare'),
            ('Which named character is drawn on page 2 and is a speaker on page 8?', 'the'),
            ('Which named character is drawn on page 2 and is a speaker on page 8 and is drawn on page 9?', 'the')]
        for question, op in cases:
            with self.subTest(question=question):
                self.assertEqual(parse_gloss(question)['op'], op)

    def test_direction(self):
        ast = parse_gloss('Compared with page 9, does page 2 contain more text regions, fewer, or the same number?')
        self.assertEqual(ast['args'][0], call('count', call('texts', call('page', 2))))
        self.assertEqual(ast['args'][1], call('count', call('texts', call('page', 9))))

    def test_unknown_and_added_claims_rejected(self):
        for question in ('How many people are on page 2?', 'How many text regions are shown on page 0?',
                         'Which named character is happy on page 2 and is drawn on page 3?',
                         'Is Goku drawn on page 2? Explain why.', 'Which named character is drawn on page 2?'):
            with self.subTest(question=question), self.assertRaises(ValueError):
                parse_gloss(question)


class RecordTests(unittest.TestCase):
    def test_no_answer_or_proof_in_model_messages(self):
        source = item(); before = copy.deepcopy(source)
        request, private = p.make_record(source)
        payload = json.loads(request['messages'][1]['content'])
        self.assertEqual(set(payload), {'template_question', 'canonical_program', 'answer_type', 'page_indexing'})
        self.assertNotIn('8', json.dumps(payload))
        self.assertEqual(private['source_item'], before)
        self.assertEqual(source, before)
        self.assertEqual(private['g10_status'], 'pending_qwen_round_trip')
        self.assertEqual(private['question_type'], 'graph_verified')

    def test_program_drift_rejected(self):
        source = item(); source['question'] = source['question'].replace('page 2', 'page 3')
        with self.assertRaises(ValueError): p.make_record(source)

    def test_tampered_proof_answer_and_execution_rejected(self):
        for section, field, value in [('proof_check', 'proof_valid', False),
                                      ('proof_check', 'execution_sha256', 'bad'),
                                      ('answer', 'value', 9), ('execution', 'eligible_for_generation', False)]:
            source = item(); source[section][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): p.make_record(source)

    def test_request_ids_stable_and_content_bound(self):
        source = item(); a = p.make_record(source)[0]
        self.assertEqual(a, p.make_record(copy.deepcopy(source))[0])
        source['item_id'] = 'q:two'
        self.assertNotEqual(a['request_id'], p.make_record(source)[0]['request_id'])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.source = self.root / 'gen1'; self.out = self.root / 'verb1'
        config = {'chapters': ['chapter']}; fingerprint = p.stable(config)
        payload = {'chapter_id': 'chapter', 'items': [item()], 'inputs_sha256': {}, 'counts': {'selected': 1}}
        name = 'chapters/chapter.json'
        p.write(self.source / name, {'fingerprint': fingerprint, 'payload_sha256': p.stable(payload), 'payload': payload})
        p.write(self.source / 'manifest.json', {'schema': 'comics_qa.gen1.build.v1', 'config': config,
                'fingerprint': fingerprint, 'counts': {'selected': 1},
                'outputs_sha256': {name: p.digest((self.source / name).read_bytes())}})

    def run_cli(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return p.main(['--source', str(self.source), '--out', str(self.out), *extra])

    def test_completed_resume_and_no_overwrite(self):
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(self.run_cli(), 2)
        self.assertEqual(self.run_cli('--resume'), 0)
        manifest = p.verify_manifest(self.out)
        self.assertEqual(manifest['counts'], {'chapters': 1, 'items': 1})

    def test_modified_output_detected(self):
        self.run_cli(); (self.out / 'report.json').write_text('{}')
        self.assertEqual(self.run_cli('--resume'), 2)

    def test_modified_source_detected(self):
        (self.source / 'chapters/chapter.json').write_text('{}')
        self.assertEqual(self.run_cli(), 2)

    def test_unknown_chapter_and_overlap_rejected(self):
        self.assertEqual(self.run_cli('--chapter', 'missing'), 2)
        self.assertEqual(self.run_cli('--out', str(self.source / 'nested')), 2)

    def test_portable_source_resume(self):
        self.assertEqual(self.run_cli(), 0)
        moved = self.root / 'moved'; self.source.rename(moved); self.source = moved
        self.assertEqual(self.run_cli('--resume'), 0)

    def test_interruption_and_partial_resume(self):
        original = p.write
        def interrupt(path, payload):
            if Path(path).name == 'report.json': raise KeyboardInterrupt
            return original(path, payload)
        with patch.object(p, 'write', interrupt):
            self.assertEqual(self.run_cli(), 130)
        self.assertFalse(self.out.exists())
        self.assertEqual(self.run_cli('--resume'), 0)

    def test_changed_code_rejected_on_resume(self):
        self.run_cli()
        with patch.object(p, 'code_hashes', return_value={'changed': 'hash'}):
            self.assertEqual(self.run_cli('--resume'), 2)

    def test_unsafe_manifest_path(self):
        with self.assertRaises(ValueError): p.inside(self.source, '../escape')
        with self.assertRaises(ValueError): p.inside(self.source, '/tmp/escape')


if __name__ == '__main__': unittest.main()
