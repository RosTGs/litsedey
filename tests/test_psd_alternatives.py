import tempfile,unittest
from PIL import Image
from psd_tools import PSDImage
from studio.storage import Store
from studio.model import new_project,mesh_layer
class PsdAlternatives(unittest.TestCase):
 def test_hidden_expression_has_editable_pixels(self):
  with tempfile.TemporaryDirectory() as root:
   store=Store(root);p=new_project('test',32,32)
   n=mesh_layer('open mouth',store.put_image(Image.new('RGBA',(8,8),'red')),(8,8,8,8))
   n['opacity_keys']={'ParamMouthOpenY':[dict(value=0,opacity=0),dict(value=1,opacity=1)]};p['layers']=[n]
   r=store.export(p,'psd');psd=PSDImage.open(store.path('exports',r['file']))
   self.assertFalse(psd[0].visible);self.assertIsNotNone(psd[0].topil().getbbox())
