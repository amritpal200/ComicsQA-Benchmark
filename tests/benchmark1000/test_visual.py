import copy
from pathlib import Path
import tempfile
import unittest
import test_crl
from comics_qa.benchmark1000.assets import render
from comics_qa.benchmark1000.visual import bind_reference, predicate, check_predicate
from comics_qa.benchmark1000.io import digest


class VisualReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_crl.ExecutionTest.setUpClass.__func__(cls)

    def setUp(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow required')
        test_crl.ExecutionTest.setUp(self)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        nodes = {n['id']: n for n in self.g['nodes']}
        self.app = next(n for n in self.g['nodes'] if n['type'] == 'Appearance' and n['id'].endswith('hchar00'))
        page = nodes[self.app['page_id']]
        self.image = self.root / 'page.png'; self.crop = self.root / 'reference.png'
        Image.new('RGB', (page['width'], page['height']), (30, 50, 70)).save(self.image)
        page['image_path'] = str(self.image); page['image_sha256'] = digest(self.image)
        render(self.image, page['image_sha256'], [self.app['box']], self.crop, 'crop')

    def test_name_free_reference_and_independent_probe(self):
        ref = bind_reference(self.g, self.app['id'], self.crop)
        doc = predicate(self.g, self.v, ref, 'present', self.app['page_id'])
        self.assertTrue(check_predicate(self.g, self.v, doc)['proof_valid'])
        bad = copy.deepcopy(doc); bad['result']['value'] = not doc['result']['value']
        self.assertFalse(check_predicate(self.g, self.v, bad)['proof_valid'])

    def test_wrong_crop_pixels_are_not_accepted(self):
        from PIL import Image
        from comics_qa.benchmark1000.io import read
        import json
        Image.new('RGB', (10, 10), (255, 255, 255)).save(self.crop)
        manifest_path = self.crop.with_suffix('.png.json')
        manifest = read(manifest_path); manifest['image_sha256'] = digest(self.crop)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            bind_reference(self.g, self.app['id'], self.crop)
