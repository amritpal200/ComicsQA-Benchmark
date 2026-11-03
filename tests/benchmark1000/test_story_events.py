import copy
import json
from pathlib import Path
import tempfile
import unittest
from comics_qa.benchmark1000.io import publish, read
from comics_qa.benchmark1000.story_check import check
from comics_qa.benchmark1000.story_events import DEFAULTS, chapter, moment, question_clause, record_audit, usable_facts
from comics_qa.benchmark1000.story_profile import profile
from test_story_families import C, world

CFG = dict(DEFAULTS, per_family=4, audit_basis='ai')


def event(n, page, who):
    return {'fact_id': f'event:{n}', 'chapter_id': C, 'page_id': f'{C}__p{page:03d}', 'panel_index': 0,
            'statement': f'On the left, the outlined character with a red scarf grips a lantern number {n}.',
            'appearance_id': f'{C}__p{page:03d}__hchar9{n}', 'identity_id': who, 'is_char_fact': f'f:ev{n}',
            'control_appearance_id': 'x', 'caption_sha256': 'c', 'images': {}, 'origin': 'M',
            'confirmation': {'model': 'm', 'positive': 'yes', 'control': 'no'}, 'tier': 'A_candidate', 'audit': 'pending'}


def setup(presence=None):
    presence = presence or {1: ['s__rin'], 2: ['s__yukio'], 3: ['s__mephisto'], 4: ['s__shiro'], 5: ['s__rin'], 6: ['s__yukio']}
    g, v, r = world(presence=presence)
    facts = [event(1, 1, 's__rin'), event(2, 3, 's__mephisto'), event(3, 4, 's__shiro'), event(4, 6, 's__yukio')]
    for f in facts:
        g['facts'].append({'fact_id': f['is_char_fact'], 'rel': 'is_char', 'args': [f['appearance_id'], f['identity_id']], 'origin': 'H', 'answer_eligible': True})
    return g, v, r, facts


class StoryEventTests(unittest.TestCase):
    def test_wording_helpers(self):
        s = 'In the foreground, the outlined character with spiky hair grips a fork.'
        self.assertEqual(question_clause(s), 'in the foreground, which named character with spiky hair grips a fork')
        self.assertEqual(moment('The outlined character waves.'), 'Someone waves.')

    def test_actor_choice_and_order_verify(self):
        g, v, r, facts = setup()
        events = {f['fact_id']: f for f in facts}
        items = chapter(g, v, r, facts, CFG)['items']
        actor = [i for i in items if i['family'] == 'event_actor_choice']
        order = [i for i in items if i['family'] == 'event_order']
        self.assertTrue(actor and order)
        for item in items:
            self.assertEqual(check(item, g, v, r, CFG, events=events), {'verified': True, 'errors': []})
            self.assertEqual(item['verification']['human'], 'required')
            self.assertIn('needs_human_verification', item['verification']['flags'])
            self.assertTrue(profile(item)['human_required'])
            self.assertEqual(profile(item)['content_category'], 'event')
            self.assertNotIn('outlined', item['question'])
        a = actor[0]; page = a['evidence']['events'][0]['page_id']
        self.assertEqual(a['evidence']['lines'][0]['page_id'], page)
        drawn = {f['args'][0] for f in g['facts'] if f['rel'] == 'present' and f['args'][1] == page}
        self.assertEqual([o['identity_id'] for o in a['options'] if o['identity_id'] in drawn], [a['answer']['identity_id']])
        pos = {p: i for i, p in enumerate(g['page_ids'])}
        by = {e['fact_id']: e for e in order[0]['evidence']['events']}
        self.assertEqual(order[0]['answer']['value'], [o['letter'] for o in sorted(order[0]['options'], key=lambda o: pos[by[o['fact_id']]['page_id']])])

    def test_checker_rejects_unconfirmed_drawn_distractor_and_tampering(self):
        g, v, r, facts = setup()
        events = {f['fact_id']: f for f in facts}
        a = next(i for i in chapter(g, v, r, facts, CFG)['items'] if i['family'] == 'event_actor_choice')
        bad_events = copy.deepcopy(events); bad_events[a['evidence']['events'][0]['fact_id']]['confirmation']['control'] = 'yes'
        self.assertFalse(check(a, g, v, r, CFG, events=bad_events)['verified'])
        self.assertIn('event_not_confirmed:' + a['evidence']['events'][0]['fact_id'], check(a, g, v, r, CFG, events={})['errors'])
        page = int(a['evidence']['events'][0]['page_id'][-3:])
        distractor = next(o['identity_id'] for o in a['options'] if o['identity_id'] != a['answer']['identity_id'])
        g2, v2, r2, _ = setup({**{p: ['s__rin'] for p in range(1, 7)}, page: ['s__rin', 's__yukio', 's__mephisto', 's__shiro', 's__kuro']})
        for f in facts:
            g2['facts'].append({'fact_id': f['is_char_fact'], 'rel': 'is_char', 'args': [f['appearance_id'], f['identity_id']], 'origin': 'H', 'answer_eligible': True})
        self.assertIn('distractor_drawn_on_page', check(a, g2, v2, r2, CFG, events=events)['errors'])
        bad = copy.deepcopy(a); bad['answer']['value'] = 'A' if bad['answer']['value'] != 'A' else 'B'
        self.assertIn('gold', check(bad, g, v, r, CFG, events=events)['errors'])

    def test_audit_intake(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); facts = root / 'facts'
            publish(facts / 'facts.json', {'facts': [event(1, 1, 's__rin'), event(2, 2, 's__yukio')]})
            publish(facts / 'report.json', {'audit_ids': ['event:1', 'event:2']})
            def decisions(name, rows):
                (root / name).write_text(json.dumps({'decisions': rows})); return root / name
            ok = decisions('ok.json', [{'fact_id': 'event:1', 'verdict': 'correct', 'reviewer': 'A'}, {'fact_id': 'event:2', 'verdict': 'wrong', 'reviewer': 'A'}])
            self.assertEqual(record_audit(facts, ok, root / 'audit', max_errors=1)['status'], 'passed')
            kept, audit = usable_facts(facts, root / 'audit')
            self.assertEqual([f['fact_id'] for f in kept], ['event:1'])  # audited-wrong facts are never used
            self.assertEqual(record_audit(facts, ok, root / 'audit0', max_errors=0)['status'], 'failed')
            with self.assertRaises(ValueError):
                usable_facts(facts, root / 'audit0')
            with self.assertRaises(ValueError):
                record_audit(facts, decisions('part.json', [{'fact_id': 'event:1', 'verdict': 'correct', 'reviewer': 'A'}]), root / 'a2')
            with self.assertRaises(ValueError):
                record_audit(facts, decisions('anon.json', [{'fact_id': f, 'verdict': 'correct'} for f in ('event:1', 'event:2')]), root / 'a3')


if __name__ == '__main__':
    unittest.main()
