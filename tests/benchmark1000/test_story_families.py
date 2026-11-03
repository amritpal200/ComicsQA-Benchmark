import copy
import unittest
from comics_qa.benchmark1000.contract import validate
from comics_qa.benchmark1000.story_check import check, check_pair
from comics_qa.benchmark1000.story_families import DEFAULTS, World, chapter, distinctiveness
from comics_qa.benchmark1000.story_profile import profile

C = 's__c001'
NAMES = {'s__rin': 'Rin', 's__yukio': 'Yukio', 's__mephisto': 'Mephisto', 's__shiro': 'Shiro', 's__kuro': 'Kuro'}
LINES = [  # (page, speaker, quote)
    (1, 's__rin', 'i will become stronger than anyone else'),
    (2, 's__yukio', 'class will now begin for every student'),
    (3, 's__mephisto', 'welcome to the academy of exorcists'),
    (4, 's__shiro', 'never let your guard down out there'),
    (5, 's__rin', 'that demon looked straight through me'),
    (6, 's__yukio', 'the ritual must stay hidden from them'),
]


def fact(i, rel, *args):
    return {'fact_id': f'f:{rel}{i}', 'rel': rel, 'args': list(args), 'origin': 'H', 'answer_eligible': True}


def world(lines=LINES, presence=None, names=NAMES, open_pages=()):
    pages = [f'{C}__p{n:03d}' for n in range(1, 7)]
    facts, transcripts = [], []
    for i, (p, who, quote) in enumerate(lines):
        text, app, page = f'{C}__p{p:03d}__htext{i:02d}', f'{C}__p{p:03d}__hchar{i:02d}', pages[p - 1]
        facts += [fact(i, 'on_page', text, page), fact(i, 'is_line', text), fact(i, 'spoken_by', text, app),
                  fact(i, 'is_char', app, who)]
        transcripts.append({'id': f'transcript:{i}', 'text_id': text, 'consensus': quote, 'magi_text': quote.upper(),
                            'paddle_text': quote, 'quote_eligible': True})
    presence = presence or {p: list(NAMES) for p in range(1, 7)}
    for j, (who, p) in enumerate([(w, p) for p in presence for w in presence[p]]):
        facts.append(fact(100 + j, 'present', who, pages[p - 1]))
    coverage = [{'page_id': pg, 'family': f, 'status': 'open' if n + 1 in open_pages else 'closed_assumed', 'coverage_id': f'cov:{n}{f}'}
                for n, pg in enumerate(pages) for f in ('char_boxes', 'names', 'text_boxes', 'speaker_links')]
    chars = [{'id': k, 'type': 'Character', 'generic': k.startswith('s__unnamed')} for k in list(NAMES) + ['s__unnamed1']]
    g = {'chapter_id': C, 'page_ids': pages, 'facts': facts, 'coverage': coverage,
         'nodes': [{'id': C, 'type': 'Chapter', 'split': 'seen'}] + chars}
    v = {'visibility': [{'identity_id': k, 'canonical_name': n, 'canonical_visible': True, 'generic': False,
                         'verified_forms': [n], 'verified_evidence_ids': ['namevis:' + k]} for k, n in names.items()]}
    return g, v, {'transcripts': transcripts}


CFG = dict(DEFAULTS, per_family=4)


class StoryFamilyTests(unittest.TestCase):
    def setUp(self):
        self.g, self.v, self.r = world()
        self.items = chapter(self.g, self.v, self.r, CFG)['items']
        self.mc = [i for i in self.items if i['family'] == 'quote_speaker_choice' and 'contrast' not in i]
        self.order = [i for i in self.items if i['family'] == 'quote_order']

    def test_generates_verified_items_without_page_numbers(self):
        self.assertEqual(len(self.mc), 4)
        self.assertGreaterEqual(len(self.order), 1)
        for item in self.items:
            self.assertTrue(check(item, self.g, self.v, self.r, CFG)['verified'], item['question'])
            self.assertNotIn('page', item['question'].lower())
            self.assertEqual(validate(item), item)

    def test_gold_letter_rotates_and_matches_speaker(self):
        self.assertEqual([i['answer']['value'] for i in self.mc], ['A', 'B', 'C', 'D'])
        for item in self.mc:
            gold = next(o for o in item['options'] if o['letter'] == item['answer']['value'])
            self.assertEqual(gold['identity_id'], item['evidence']['lines'][0]['speaker'])
        self.assertTrue(all(i['features']['two_option'] is False for i in self.items))

    def test_order_answer_follows_pages(self):
        item = self.order[0]
        pages = {l['text_id']: self.g['page_ids'].index(l['page_id']) for l in item['evidence']['lines']}
        letters = {o['letter']: pages[o['text_id']] for o in item['options']}
        self.assertEqual(item['answer']['value'], sorted(letters, key=letters.get))
        self.assertNotEqual(item['answer']['value'], list('ABCD'))

    def test_checker_rejects_tampering(self):
        bad = copy.deepcopy(self.mc[0]); bad['answer']['value'] = 'D' if bad['answer']['value'] != 'D' else 'A'
        self.assertFalse(check(bad, self.g, self.v, self.r, CFG)['verified'])
        bad = copy.deepcopy(self.order[0]); bad['answer']['value'] = list(reversed(bad['answer']['value']))
        self.assertIn('order', check(bad, self.g, self.v, self.r, CFG)['errors'])
        bad = copy.deepcopy(self.mc[0]); bad['question'] = bad['question'].replace('Who says', 'On page 3, who says')
        self.assertFalse(check(bad, self.g, self.v, self.r, CFG)['verified'])
        v = copy.deepcopy(self.v); gold = self.mc[0]['answer']
        next(x for x in v['visibility'] if x['identity_id'] == gold['identity_id'])['verified_forms'] = []
        self.assertIn('name_not_readable:' + gold['display'], check(self.mc[0], self.g, v, self.r, CFG)['errors'])

    def test_similar_or_contained_quote_is_not_distinct(self):
        t = self.r['transcripts']
        self.assertTrue(distinctiveness(t[0]['consensus'], t[0]['id'], t, 0.6)['passed'])
        echo = dict(t[1], id='transcript:x', consensus=None, magi_text='I WILL BECOME STRONGER THAN ANYONE ELSE!!')
        self.assertFalse(distinctiveness(t[0]['consensus'], t[0]['id'], t + [echo], 0.6)['passed'])
        near = dict(t[1], id='transcript:y', consensus=None, magi_text=None, paddle_text='i will become stronger than everyone')
        self.assertFalse(distinctiveness(t[0]['consensus'], t[0]['id'], t + [near], 0.6)['passed'])
        g, v, r = world(); r['transcripts'].append(echo)
        self.assertNotIn(g['facts'][0]['args'][0], [l['text_id'] for l in World(g, v, r).lines(CFG)])

    def test_line_with_inner_double_quotes_is_skipped(self):
        g, v, r = world([(1, 's__rin', 'you will begin as a "page" here today')] + LINES[1:])
        self.assertNotIn(g['facts'][0]['args'][0], [l['text_id'] for l in World(g, v, r).lines(CFG)])

    def test_option_name_inside_quote_is_skipped(self):
        lines = [(1, 's__rin', 'yukio will never understand me at all')] + LINES[1:]
        g, v, r = world(lines)
        items = chapter(g, v, r, CFG)['items']
        self.assertFalse(any('yukio will never' in i['question'] for i in items if i['family'] == 'quote_speaker_choice'))

    def test_open_answer_when_too_few_readable_names(self):
        g, v, r = world(names={k: NAMES[k] for k in ('s__rin', 's__yukio', 's__mephisto')})
        items = chapter(g, v, r, CFG)['items']
        open_items = [i for i in items if i['family'] == 'quote_speaker_open']
        self.assertTrue(open_items)
        self.assertFalse(any(i['family'] == 'quote_speaker_choice' for i in items))  # also no choice pairs with 3 names
        for item in open_items:
            self.assertTrue(check(item, g, v, r, CFG)['verified'])
            self.assertEqual(item['question'], 'Who says "' + item['evidence']['lines'][0]['quote'] + '"?')
        bad = copy.deepcopy(open_items[0]); bad['answer']['identity_id'] = 's__shiro'
        self.assertFalse(check(bad, g, v, r, CFG)['verified'])

    def test_conversation_partner_needs_unique_partner_and_closed_coverage(self):
        presence = {1: ['s__rin', 's__yukio', 's__unnamed1'], 2: ['s__yukio', 's__rin', 's__mephisto'], 3: ['s__mephisto', 's__shiro'],
                    4: ['s__shiro'], 5: ['s__rin', 's__kuro'], 6: ['s__yukio', 's__kuro']}
        g, v, r = world(presence=presence, open_pages=(6,))
        items = [i for i in chapter(g, v, r, CFG)['items'] if i['family'] == 'conversation_partner']
        got = {i['evidence']['lines'][0]['page_id'][-1]: i['answer']['value'] for i in items}
        self.assertEqual(got, {'1': 'Yukio', '3': 'Shiro', '5': 'Kuro'})  # p2: two others; p4: none; p6: open coverage
        for item in items:
            self.assertTrue(check(item, g, v, r, CFG)['verified'])
            self.assertNotIn('page', item['question'].lower().replace('same page', ''))
        g2, v2, r2 = world(presence={**presence, 1: ['s__rin', 's__yukio', 's__shiro']})
        p1 = next(i for i in items if i['answer']['value'] == 'Yukio')
        self.assertIn('partner_not_unique', check(p1, g2, v2, r2, CFG)['errors'])
        g3, v3, r3 = world(presence=presence, open_pages=(1,))
        self.assertIn('coverage_open', check(p1, g3, v3, r3, CFG)['errors'])

    def test_next_speech_partner(self):
        presence = {1: ['s__rin', 's__yukio', 's__unnamed1'], 2: ['s__yukio', 's__rin', 's__mephisto'], 3: ['s__mephisto', 's__shiro'],
                    4: ['s__shiro'], 5: ['s__rin', 's__kuro'], 6: ['s__yukio', 's__kuro']}
        g, v, r = world(presence=presence)
        items = [i for i in chapter(g, v, r, CFG)['items'] if i['family'] == 'next_speech_partner']
        # Rin: p1 -> next speaks p5 (Kuro); Yukio: p2 -> p6 (Kuro).
        self.assertEqual(sorted((i['evidence']['lines'][0]['page_id'][-1], i['evidence']['next_page'][-1], i['answer']['value']) for i in items),
                         [('1', '5', 'Kuro'), ('2', '6', 'Kuro')])
        for item in items:
            self.assertEqual(check(item, g, v, r, CFG), {'verified': True, 'errors': []})
            self.assertEqual(item['complexity']['story_hops'], 3)
        g2, v2, r2 = world(presence=presence, open_pages=(3,))
        self.assertFalse(any(i['family'] == 'next_speech_partner' for i in chapter(g2, v2, r2, CFG)['items']))
        self.assertIn('coverage_open_between', check(items[0], g2, v2, r2, CFG)['errors'])
        bad = copy.deepcopy(items[0]); bad['evidence']['next_page'] = g['page_ids'][5]
        self.assertIn('next_page', check(bad, g, v, r, CFG)['errors'])

    def test_shared_character(self):
        presence = {1: ['s__rin', 's__kuro'], 2: ['s__yukio'], 3: ['s__mephisto'], 4: ['s__shiro', 's__kuro'], 5: ['s__rin'], 6: ['s__yukio']}
        g, v, r = world(presence=presence)
        items = [i for i in chapter(g, v, r, CFG)['items'] if i['family'] == 'shared_character']
        self.assertEqual([i['answer']['value'] for i in items], ['Kuro'])
        self.assertEqual(check(items[0], g, v, r, CFG), {'verified': True, 'errors': []})
        g2, v2, r2 = world(presence={**presence, 4: ['s__shiro', 's__kuro', 's__mephisto'], 1: ['s__rin', 's__kuro', 's__mephisto']})
        self.assertIn('shared_not_unique', check(items[0], g2, v2, r2, CFG)['errors'])
        g3, v3, r3 = world(presence={**presence, 4: ['s__shiro', 's__rin'], 1: ['s__rin']})
        self.assertFalse(any(i['family'] == 'shared_character' for i in chapter(g3, v3, r3, CFG)['items']))  # Rin speaks one line

    def test_contrast_pairs(self):
        presence = {1: ['s__rin', 's__yukio', 's__unnamed1'], 2: ['s__yukio', 's__rin', 's__mephisto'], 3: ['s__mephisto', 's__shiro'],
                    4: ['s__shiro'], 5: ['s__rin', 's__kuro'], 6: ['s__yukio', 's__kuro']}
        g, v, r = world(presence=presence)
        items = [i for i in chapter(g, v, r, CFG)['items'] if 'contrast' in i]
        pairs = {}
        for i in items: pairs.setdefault(i['contrast']['pair_id'], []).append(i)
        kinds = sorted(p[0]['contrast']['kind'] for p in pairs.values())
        self.assertIn('choice', kinds); self.assertIn('partner', kinds)
        for pair in pairs.values():
            self.assertEqual(check_pair(pair), [])
            self.assertNotEqual(pair[0]['answer']['value'], pair[1]['answer']['value'])
            for m in pair:
                self.assertTrue(check(m, g, v, r, CFG)['verified'])
                self.assertEqual(validate(m), m)
                self.assertEqual(profile(m)['content_category'], 'contrast')
        partner = next(p for p in pairs.values() if p[0]['contrast']['kind'] == 'partner')
        self.assertEqual(sorted(m['answer']['value'] for m in partner), ['Kuro', 'Yukio'])  # Rin on p1 and p5
        choice = next(p for p in pairs.values() if p[0]['contrast']['kind'] == 'choice')
        bad = copy.deepcopy(choice); bad[1]['options'] = list(reversed(bad[1]['options']))
        self.assertIn('pair_options_differ', check_pair(bad))
        self.assertEqual(check_pair(choice[:1]), ['pair_incomplete'])

    def test_profile_categories(self):
        self.assertEqual(profile(self.mc[0])['content_category'], 'dialogue')
        p = profile(self.order[0])
        self.assertEqual((p['content_category'], p['page_reference'], p['anchor_type']), ('story_order', False, 'quote'))


if __name__ == '__main__':
    unittest.main()
