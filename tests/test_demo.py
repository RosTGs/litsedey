import copy
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from server import App
from studio.demo import seed_demo
from studio.model import validate
from studio.rig import render_scene
from studio.storage import Store


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.p = seed_demo(self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_demo_bundle_preserves_editable_forms_and_pixels(self):
        validate(self.p)
        result = self.store.export(self.p, 'bundle')
        other = self.store.import_bundle(self.store.path('exports', result['file']).read_bytes())
        self.assertNotEqual(other['id'], self.p['id'])
        self.assertEqual(other['tracks'], self.p['tracks'])
        self.assertEqual(other['parameters'], self.p['parameters'])
        for a, b in zip(self.p['layers'], other['layers']):
            for field in ('vertices', 'uv', 'triangles', 'keys'):
                self.assertEqual(a[field], b[field])
            with Image.open(self.store.path('assets', a['asset'])) as x, Image.open(self.store.path('assets', b['asset'])) as y:
                self.assertEqual(x.tobytes(), y.tobytes())

    def test_blink_is_independent_and_mouth_changes_image(self):
        images = {}
        for layer in self.p['layers']:
            with Image.open(self.store.path('assets', layer['asset'])) as image:
                images[layer['asset']] = image.convert('RGBA')
        neutral, _ = render_scene(self.p, images)
        params = copy.deepcopy(self.p['parameters'])
        next(q for q in params if q['id'] == 'ParamEyeLOpen')['value'] = 0
        blink, _ = render_scene(self.p, images, params)
        self.assertNotEqual(neutral.crop((354, 228, 403, 290)).tobytes(), blink.crop((354, 228, 403, 290)).tobytes())
        self.assertEqual(neutral.crop((235, 228, 289, 290)).tobytes(), blink.crop((235, 228, 289, 290)).tobytes())
        next(q for q in params if q['id'] == 'ParamMouthOpenY')['value'] = 1
        mouth, _ = render_scene(self.p, images, params)
        self.assertNotEqual(blink.crop((285, 285, 355, 350)).tobytes(), mouth.crop((285, 285, 355, 350)).tobytes())

    def test_all_public_demo_exports(self):
        for kind in ('bundle', 'png', 'psd', 'motion', 'expression'):
            with self.subTest(kind=kind):
                result = self.store.export(self.p, kind)
                self.assertGreater(self.store.path('exports', result['file']).stat().st_size, 0)
        with self.assertRaisesRegex(ValueError, 'настройте физику'):
            self.store.export(self.p, 'baked-motion')

    def test_seed_never_changes_existing_workspace(self):
        before = self.store.list()
        app = App(self.temp.name, Path(self.temp.name)/'settings.json')
        try:
            app.seed()
            self.assertEqual(app.store.list(), before)
            self.assertEqual(app.store.load(self.p['id']), self.p)
        finally:
            app.pool.shutdown()
