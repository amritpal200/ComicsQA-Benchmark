import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from comics_qa.benchmark1000.events import has_action, ingest, parse, statements, verify
from comics_qa.benchmark1000.io import publish, read, stable


def panel(caption, phrase, named=True, entities=1):
    a = caption.index(phrase)
    return {'caption': caption, 'phrases': [{'span_in_caption': [a, a + len(phrase)], 'entity_ids': list(range(entities)), 'text_in_caption': phrase}],
            'entities': [{'entity_id': i, 'human_character': {'status': 'matched', 'named': named, 'ref': 3 + i}} for i in range(entities)]}


class EventStatementTests(unittest.TestCase):
    def test_subject_replaced_by_outline_reference(self):
        out = statements(panel('The room is dark. In the foreground, a boy with spiky hair grips a knife and fork.', 'a boy'))
        self.assertEqual([(s, ref) for s, _, ref in out], [('In the foreground, the outlined character with spiky hair grips a knife and fork.', 3)])
        out = statements(panel('A girl raises her arm.', 'A girl'))
        self.assertEqual(out[0][0], 'The outlined character raises her arm.')

    def test_rejections(self):
        self.assertEqual(statements(panel('A boy with spiky hair and a jacket.', 'A boy')), [])            # no action
        self.assertEqual(statements(panel('A boy points at a speech bubble.', 'A boy')), [])               # about text
        self.assertEqual(statements(panel('A boy grips a sword.', 'A boy', named=False)), [])              # generic
        self.assertEqual(statements(panel('A boy grips a sword.', 'A boy', entities=2)), [])               # two entities
        long = 'A small mark floats near the head'
        self.assertEqual(statements(panel(long + ' and he grins.', long)), [])                             # not a noun phrase

    def test_parse_and_verbs(self):
        self.assertEqual([parse(x) for x in ('Yes.', ' no', 'YES, it is', 'maybe', '')], ['yes', 'no', 'yes', 'unparsed', 'unparsed'])
        self.assertTrue(has_action('she is recoiling in shock')); self.assertFalse(has_action('he has short hair'))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        text = body['messages'][0]['content'][1]['text']
        image = body['messages'][0]['content'][0]['image_url']['url']
        answer = 'yes' if image.endswith(Handler.yes_image) and 'grips' in text else 'no'
        raw = json.dumps({'choices': [{'message': {'content': answer}}]}).encode()
        self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def log_message(self, *args): pass


class EventPipelineTests(unittest.TestCase):
    def test_verify_resume_and_ingest_acceptance(self):
        import base64
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); req = root / 'req'
            (req / 'images').mkdir(parents=True)
            (req / 'images/pos.png').write_bytes(b'POSITIVE'); (req / 'images/neg.png').write_bytes(b'CONTROL')
            Handler.yes_image = base64.b64encode(b'POSITIVE').decode()
            rows = []
            for n, statement in enumerate(['The outlined character grips a sword.', 'The outlined character waves.']):
                rows.append({'fact_id': f'event:{n}', 'chapter_id': 'c', 'page_id': 'c__p1', 'panel_index': 0, 'statement': statement,
                             'appearance_id': 'c__p1__hchar00', 'identity_id': 's__rin', 'is_char_fact': 'f:1', 'control_appearance_id': 'c__p1__hchar01',
                             'caption_sha256': 'x', 'images': {'positive': 'images/pos.png', 'control': 'images/neg.png'},
                             'prompt': 'Statement: ' + statement})
            publish(req / 'requests.json', {'schema': 'comics_qa.benchmark1000.event_requests.1', 'requests': rows})
            server = HTTPServer(('127.0.0.1', 0), Handler); threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                url = f'http://127.0.0.1:{server.server_port}/v1'
                first = verify(req, url, 'fake', root / 'resp', workers=2)
                self.assertEqual((first['jobs'], first['answered']), (4, 4))
                self.assertEqual(verify(req, url, 'fake', root / 'resp', workers=2)['reused'], 4)
            finally:
                server.shutdown(); server.server_close()
            report = ingest(req, root / 'resp', root / 'facts')
            self.assertEqual(report['outcomes'], {'yes/no': 1, 'no/no': 1})
            facts = read(root / 'facts/facts.json')['facts']
            self.assertEqual([f['fact_id'] for f in facts], ['event:0'])
            self.assertEqual((facts[0]['origin'], facts[0]['tier'], facts[0]['audit']), ('M', 'A_candidate', 'pending'))
            self.assertIn('grips a sword', (root / 'facts/audit.html').read_text())


if __name__ == '__main__':
    unittest.main()
