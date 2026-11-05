import copy
import json
from pathlib import Path
import tempfile
import unittest
from comics_qa.benchmark1000.freegen import build_pack, ids_for, parse_items, resolve
from comics_qa.benchmark1000.freegen_check import Facts, _order, check_item, display
from comics_qa.benchmark1000.story_families import DEFAULTS, World
from comics_qa.benchmark1000.story_profile import profile
from test_story_expand import PAGE_LINES
from test_story_families import world


class FreeGenTests(unittest.TestCase):
    def setUp(self):
        _order.cache_clear()
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.g, self.v, self.r = world(PAGE_LINES)
        texts = {}
        for f in self.g['facts']:
            if f['rel'] == 'on_page': texts.setdefault(f['args'][1], []).append(f['args'][0])
        core = Path(self.tmp.name)
        with open(core / 'pages.jsonl', 'w') as out:
            for page, ids in texts.items():
                out.write(json.dumps({'chapter_id': self.g['chapter_id'], 'page_id': page,
                                      'texts': [{'text_id': t, 'reading_order': k} for k, t in enumerate(sorted(ids))]}) + '\n')
        self.cfg = dict(DEFAULTS, core_root=str(core))
        self.w = World(self.g, self.v, self.r)
        self.order = {t: v for t, v in _order(str(core), self.g['chapter_id']).items()}
        quotable = {l['text_id'] for l in self.w.lines(self.cfg)}
        self.pack, self.idmap = build_pack(self.w, self.order, [], self.g['page_ids'], quotable, 'chapter')
        self.cid, self.pid, self.lid, _ = ids_for(self.w, self.order, [])
        self.request = {'request_id': 'fg:x', 'level': 'chapter', 'pack_pages': self.g['page_ids'], 'idmap': self.idmap}

    def item(self, prop):
        core, err = resolve(prop, self.request)
        self.assertIsNone(err)
        F = Facts(self.g, self.v, self.r, self.cfg['core_root'], {})
        ans = core['answer']
        if ans['type'] == 'sequence': ans['value'] = [display(F, 'L', x) for x in ans['refs']]
        else: ans['value'] = display(F, {'character': 'C', 'page': 'P', 'quote': 'L'}[core['answer_format']], ans['ref'])
        multi_page_seq = ans['type'] == 'sequence' and len({F.page_of[x] for x in ans['refs']}) == len(ans['refs'])
        same_page = any(c['type'] in ('NEXT_LINE',) or (c['type'] == 'BEFORE' and F.page_of[c['args'][0]] == F.page_of[c['args'][1]]) for c in core['claims'])
        used = ['magi_reading_order'] if same_page or (ans['type'] == 'sequence' and not multi_page_seq) else []
        return {'family': 'free_generation', 'question': core['question'], 'answer_format': core['answer_format'], 'answer': ans,
                'evidence': {'claims': core['claims'], 'lines': []}, 'track': 'experimental', 'uses_model_facts': used,
                'verification': {'flags': ['needs_human_verification', 'needs_uniqueness_check']}}

    def line(self, quote):
        tid = next(f['args'][0] for f in self.g['facts'] if f['rel'] == 'on_page' and any(
            t['text_id'] == f['args'][0] and t['consensus'] == quote for t in self.r['transcripts']))
        return self.lid[tid]

    def test_pack_has_ids_names_and_quotable_marks(self):
        self.assertIn('C1 ', self.pack); self.assertIn('PAGE P1', self.pack)
        self.assertIn('*', self.pack)
        self.assertNotIn('s__', self.pack.split('CHARACTERS')[1])  # no internal graph IDs in the pack body

    def test_valid_character_and_sequence_items_verify(self):
        rin, l1 = self.cid['s__rin'], self.line('we have to hurry before the gate closes')
        it = self.item({'question': 'Who says "we have to hurry before the gate closes"?', 'answer_format': 'character', 'answer_ref': rin,
                        'claims': [f'SAYS({l1},{rin})']})
        self.assertEqual(check_item(it, self.g, self.v, self.r, self.cfg, {}), {'verified': True, 'errors': []})
        self.assertEqual(profile(dict(it, schema='comics_qa.benchmark1000.story_item.1'))['content_category'], 'dialogue')
        a, b, c = (self.line(q) for q in ('the ritual must stay hidden from them', 'that demon looked straight through me',
                                          'class will now begin for every student'))
        seq = self.item({'question': 'Put these lines in story order: "the ritual must stay hidden from them", "class will now begin for every student", '
                                     '"that demon looked straight through me".', 'answer_format': 'line_sequence', 'answer_ref': [a, b, c],
                         'claims': [f'BEFORE({a},{b})', f'BEFORE({b},{c})']})
        self.assertEqual(check_item(seq, self.g, self.v, self.r, self.cfg, {})['errors'], [])

    def test_rejections(self):
        rin, yukio, l1 = self.cid['s__rin'], self.cid['s__yukio'], self.line('we have to hurry before the gate closes')
        false = self.item({'question': 'Who says "we have to hurry before the gate closes"?', 'answer_format': 'character',
                           'answer_ref': yukio, 'claims': [f'SAYS({l1},{yukio})']})
        self.assertIn('claim_false:SAYS', check_item(false, self.g, self.v, self.r, self.cfg, {})['errors'])
        leak = self.item({'question': f'Which character, {rin} or Rin, says "we have to hurry before the gate closes"?', 'answer_format': 'character',
                          'answer_ref': rin, 'claims': [f'SAYS({l1},{rin})']})
        errs = check_item(leak, self.g, self.v, self.r, self.cfg, {})['errors']
        self.assertIn('pack_id_in_question', errs); self.assertIn('answer_in_question', errs)
        self.assertEqual(resolve({'question': 'x', 'answer_format': 'character', 'answer_ref': 'C99', 'claims': ['SAYS(L1.1,C99)']}, self.request)[1], 'unknown_id')
        self.assertEqual(resolve({'question': 'x', 'answer_format': 'yes_no', 'answer_ref': 'C1', 'claims': []}, self.request)[1], 'answer_format')
        noflag = copy.deepcopy(false); noflag['track'] = 'official'
        self.assertIn('flags', check_item(noflag, self.g, self.v, self.r, self.cfg, {})['errors'])

    def test_parse_items(self):
        self.assertEqual(parse_items('<think>maybe [1]?</think> Here: ```json\n[{"q": 1}]\n```'), [{'q': 1}])
        self.assertEqual(parse_items('reasoning [1] ...</think>\n[{"q": 2}]'), [{'q': 2}])
        self.assertIsNone(parse_items('no list here'))


if __name__ == '__main__':
    unittest.main()
