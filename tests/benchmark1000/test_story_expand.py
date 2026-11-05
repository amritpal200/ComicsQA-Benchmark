import copy
import unittest
from comics_qa.benchmark1000.contract import validate
from comics_qa.benchmark1000.story_check import check
from comics_qa.benchmark1000.story_expand import DEFAULTS, chapter, generate
from comics_qa.benchmark1000.story_families import DEFAULTS as STORY_DEFAULTS
from comics_qa.benchmark1000.story_profile import profile
from test_story_families import LINES, world

CFG = dict(STORY_DEFAULTS, **DEFAULTS)
PAGE_LINES = [  # four speakers on page 1, one line each on later pages
    (1, 's__rin', 'we have to hurry before the gate closes'),
    (1, 's__yukio', 'the ritual must stay hidden from them'),
    (1, 's__mephisto', 'welcome to the academy of exorcists'),
    (1, 's__shiro', 'never let your guard down out there'),
    (2, 's__kuro', 'that demon looked straight through me'),
    (3, 's__yukio', 'class will now begin for every student'),
    (4, 's__rin', 'mephisto would never allow such a thing'),
    (5, 's__rin', 'i can feel the flames under my skin'),
    (5, 's__yukio', 'please return the textbooks by friday'),
    (5, 's__mephisto', 'the cram school opens its doors tonight'),
    (5, 's__kuro', 'the city lights are beautiful from up here'),
]


def by_family(items, fam):
    return [i for i in items if i['family'] == fam]


class StoryExpandTests(unittest.TestCase):
    def test_script_error_and_speaker_table(self):
        g, v, r = world()
        items = chapter(g, v, r, CFG)['items']
        se, st = by_family(items, 'script_error'), by_family(items, 'speaker_table')
        self.assertTrue(se and st)
        for item in se + st:
            self.assertEqual(check(item, g, v, r, CFG), {'verified': True, 'errors': []})
            self.assertEqual(validate(item), item)
            self.assertEqual(profile(item)['question_form'], item['family'])
            self.assertNotIn('page', item['question'].lower())
        rows = se[0]['evidence']['rows']
        wrong = se[0]['answer']['value']
        self.assertEqual(len(wrong), 2)
        bad = copy.deepcopy(se[0]); bad['answer']['value'] = [1, 2] if wrong != [1, 2] else [3, 4]
        self.assertIn('answer', check(bad, g, v, r, CFG)['errors'])
        bad = copy.deepcopy(st[0]); bad['answer']['value'] = list(reversed(bad['answer']['value']))
        if bad['answer']['value'] != st[0]['answer']['value']:
            self.assertIn('answer', check(bad, g, v, r, CFG)['errors'])
        self.assertEqual(len(rows), 6)

    def test_name_trap(self):
        g, v, r = world(PAGE_LINES)
        nt = by_family(chapter(g, v, r, CFG)['items'], 'name_trap')
        self.assertEqual(len(nt), 1)  # Rin's line names Mephisto
        item = nt[0]
        self.assertEqual(item['answer']['display'], 'Rin')
        self.assertIn('Mephisto', [o['text'] for o in item['options']])
        self.assertEqual(check(item, g, v, r, CFG), {'verified': True, 'errors': []})
        bad = copy.deepcopy(item); bad['answer']['identity_id'] = 's__mephisto'
        self.assertIn('gold', check(bad, g, v, r, CFG)['errors'])

    def test_line_of_character_both_cases(self):
        g, v, r = world(PAGE_LINES)
        cfg = dict(CFG, per_family=2)
        items = by_family(generate(g, v, r, cfg)[0], 'line_of_character')
        self.assertEqual(sorted(i['answer']['says_nothing'] for i in items), [False, True])
        for item in items:
            self.assertEqual(check(item, g, v, r, cfg), {'verified': True, 'errors': []})
            gold = next(o for o in item['options'] if o['letter'] == item['answer']['value'])
            if item['answer']['says_nothing']:
                self.assertTrue(gold['text'].endswith('says nothing on that page'))
            else:
                self.assertIsNotNone(gold['text_id'])
        g2, v2, r2 = world(PAGE_LINES, open_pages=(1, 5))  # both qualifying pages open -> nothing can be claimed
        self.assertFalse(by_family(generate(g2, v2, r2, cfg)[0], 'line_of_character'))
        for item in items:
            self.assertIn('coverage_open', check(item, g2, v2, r2, cfg)['errors'])
        absent = next(i for i in items if i['answer']['says_nothing'])
        bad = copy.deepcopy(absent); bad['answer']['value'] = next(o['letter'] for o in bad['options'] if o['text_id'])
        self.assertIn('answer', check(bad, g, v, r, cfg)['errors'])

    def test_existing_families_unchanged(self):
        g, v, r = world(LINES)
        from comics_qa.benchmark1000.story_families import chapter as story_chapter
        for item in story_chapter(g, v, r, STORY_DEFAULTS)['items']:
            self.assertEqual(check(item, g, v, r, STORY_DEFAULTS)['verified'], True)


if __name__ == '__main__':
    unittest.main()


class ExperimentalTrackTests(unittest.TestCase):
    def setUp(self):
        import json, tempfile
        from pathlib import Path
        from comics_qa.benchmark1000.story_experimental import reading_order
        from comics_qa.benchmark1000.story_expand_check import _core_order
        reading_order.cache_clear(); _core_order.cache_clear()
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.g, self.v, self.r = world(PAGE_LINES)
        texts = {}
        for f in self.g['facts']:
            if f['rel'] == 'on_page': texts.setdefault(f['args'][1], []).append(f['args'][0])
        self.core = Path(self.tmp.name)
        with open(self.core / 'pages.jsonl', 'w') as out:
            for page, ids in texts.items():
                # reversed id order = reading order, so it differs from storage order
                rows = [{'text_id': t, 'reading_order': k} for k, t in enumerate(sorted(ids, reverse=True))]
                out.write(json.dumps({'chapter_id': self.g['chapter_id'], 'page_id': page, 'texts': rows}) + '\n')
        self.cfg = dict(CFG, core_root=str(self.core))

    def test_experimental_items_are_flagged_and_verified(self):
        from comics_qa.benchmark1000.story_experimental import chapter as exp_chapter
        items = exp_chapter(self.g, self.v, self.r, self.cfg)['items']
        fams = {i['family'] for i in items}
        self.assertEqual(fams, {'next_line_speaker', 'page_line_order'})
        for item in items:
            self.assertEqual(item['track'], 'experimental')
            self.assertIn('needs_human_verification', item['verification']['flags'])
            self.assertEqual(check(item, self.g, self.v, self.r, self.cfg), {'verified': True, 'errors': []})
            self.assertEqual(profile(item)['track'], 'experimental')
        order = next(i for i in items if i['family'] == 'page_line_order')
        bad = copy.deepcopy(order); bad['answer']['value'] = list(reversed(bad['answer']['value']))
        self.assertIn('order', check(bad, self.g, self.v, self.r, self.cfg)['errors'])
        unflagged = copy.deepcopy(order); unflagged['track'] = 'official'
        self.assertIn('experimental_flags', check(unflagged, self.g, self.v, self.r, self.cfg)['errors'])
