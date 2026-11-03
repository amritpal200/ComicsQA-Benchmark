import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from comics_qa.benchmark1000.cli import main
from comics_qa.benchmark1000.io import digest, publish, read, stable
from comics_qa.benchmark1000.story_profile import load_profiles, profile, summarize, union_key

TARGETS = Path(__file__).resolve().parents[2] / 'configs/benchmark1000/story_targets_v1.json'
LEGACY = 'comics_qa.benchmark1000.candidate.1'
NATIVE = 'comics_qa.benchmark1000.admitted_native.1'
PAIRED = 'comics_qa.benchmark1000.contrast_member.1'


def legacy(fam, question, canonical='', fmt='count', value=3):
    return {'schema': LEGACY, 'question': question, 'answer_format': fmt, 'answer': {'value': value},
            'legacy': {'family': fam, 'canonical': canonical}, 'complexity': {'meaningful_hops': None}}


def native(question, structure='chain', fmt='page', value=15, hops=3, schema=NATIVE, group='chain'):
    return {'schema': schema, 'question': question, 'answer_format': fmt, 'answer': {'value': value},
            'reasoning_structure': structure, 'primary_group': group, 'complexity': {'meaningful_hops': hops}}


PROCEDURAL_Q = ('Identify the speaker of the text "nice to meet you." on page 11. Search only the inclusive range from '
                'page 12 to page 21. Start immediately before this range and follow the current person to their next '
                'speaking page two times. Which page does the final step reach?')


class StoryProfileTests(unittest.TestCase):
    def test_legacy_box_counts_are_perception(self):
        for fam, q in (('count_texts', 'How many text regions are shown on page 14?'),
                       ('compare_text_count', 'Compared with page 18, does page 3 contain more text regions, fewer, or the same number?'),
                       ('count_apps', 'How many character depictions are shown on page 33?')):
            p = profile(legacy(fam, q))
            self.assertEqual((p['content_category'], p['unit_dependence'], p['anchor_type']), ('perception', 'box_count', 'page'))
            self.assertTrue(p['page_reference'])

    def test_legacy_story_families(self):
        p = profile(legacy('quote_speaker', 'Who is the speaker of the text region reading "he was cool." on page 46?', fmt='character', value='Rin'))
        self.assertEqual((p['content_category'], p['anchor_type'], p['unit_dependence']), ('dialogue', 'quote', 'none'))
        p = profile(legacy('next_appearance', 'After Rin appears on page 5, on which later page is this character next drawn?',
                           '(next_appearance (char "Rin") (page 5))', 'page', 6))
        self.assertEqual((p['content_category'], p['anchor_type'], p['page_answer']), ('character', 'relative', True))
        p = profile(legacy('character_constraints', 'Which named character is drawn on page 9 and is drawn on page 3?',
                           '(and (drawn (page 9)) (drawn (page 3)))', 'character', 'X'))
        self.assertEqual((p['anchor_type'], p['unit_dependence']), ('page', 'page_presence'))

    def test_unknown_legacy_family_fails(self):
        with self.assertRaises(ValueError):
            profile(legacy('new_family', 'How many?'))

    def test_native_procedural_multi_hop_and_contrast(self):
        p = profile(native(PROCEDURAL_Q))
        self.assertEqual((p['content_category'], p['wording_style'], p['anchor_type'], p['story_hops']), ('multi_hop', 'procedural', 'quote', 3))
        p = profile(native('Use only pages 12 through 21. How many dialogue text regions belong to this person?', 'aggregate_compare', 'count', 4, None, group='aggregate_compare'))
        self.assertEqual((p['content_category'], p['unit_dependence'], p['count_answer']), ('perception', 'box_count', True))
        p = profile(native(PROCEDURAL_Q, schema=PAIRED))
        self.assertEqual(p['content_category'], 'contrast')
        p = profile(native('After page 12, on which page does the speaker of the text "take this." on that page next speak?', 'direct', group='unassigned'))
        self.assertEqual((p['content_category'], p['wording_style']), ('dialogue', 'natural'))

    def test_contrast_member_shares_native_key(self):
        snapshots = {'graph': 'g'}
        a = {'schema': NATIVE, 'chapter_id': 'c', 'source': {'snapshots': snapshots}, 'admission_receipt': {'resolved_path_sha256': 'r'}}
        b = dict(a, schema=PAIRED, pair_id='x', pair_role=0)
        self.assertEqual(union_key(a), union_key(b))

    def test_summary_shortfalls_and_caps(self):
        targets = read(TARGETS)
        profiles = [profile(legacy('count_texts', 'How many text regions are shown on page 2?'))] * 3 + \
                   [profile(native(PROCEDURAL_Q))]
        s = summarize(profiles, targets)
        self.assertEqual(s['candidates'], 4)
        self.assertEqual(s['caps']['box_count']['candidates'], 3)
        self.assertEqual(s['caps']['procedural']['final_max_items'], 50)
        self.assertEqual(s['categories']['multi_hop']['shortfall_natural'], 220)
        self.assertEqual(s['categories']['perception']['shortfall_natural'], 47)
        self.assertEqual(s['multi_hop_with_certified_min_hops'], 1)
        bad = dict(targets, categories=dict(targets['categories'], dialogue=1))
        with self.assertRaises(ValueError):
            summarize(profiles, bad)

    def test_cli_report_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); src = root / 'old'
            item = {'item_id': 'old:1', 'chapter_id': 'c', 'split': 'seen', 'family': 'quote_speaker',
                    'question': 'Who is the speaker of the text region reading "hi." on page 2?',
                    'answer': {'type': 'char', 'value': 'Rin', 'identity_id': 's__rin'}, 'program': {'op': 'speaker'},
                    'program_sha256': 'p', 'execution': {'program': {'op': 'speaker'}},
                    'proof_check': {'accepted_for_generation': True, 'proof_valid': True},
                    'dimensions': {'necessary_pages': ['c__p2']}}
            payload = {'chapter_id': 'c', 'split': 'seen', 'candidates': [item], 'frequent_ids': []}
            publish(src / 'candidate_pools/c.json', {'payload': payload, 'payload_sha256': stable(payload)})
            publish(src / 'manifest.json', {'config': {'chapters': ['c']}, 'outputs_sha256': {
                'candidate_pools/c.json': digest(src / 'candidate_pools/c.json')}})
            def run(args):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(args), 0)
                    return json.loads(output.getvalue())
            run(['import', '--source', str(src), '--out', str(root / 'store')])
            args = ['story-profile', '--store', str(root / 'store'), '--out', str(root / 'profile')]
            first = run(args)
            self.assertEqual(first, run(args))
            self.assertEqual(first['candidates'], 1)
            profiles = list(load_profiles(root / 'profile').values())
            self.assertEqual(profiles[0]['content_category'], 'dialogue')
            self.assertIn('| dialogue | 200 | 1 |', (root / 'profile/report.md').read_text())


if __name__ == '__main__':
    unittest.main()
