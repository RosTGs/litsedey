import json
import subprocess
import unittest
from PIL import Image
from studio.model import new_project, mesh_layer, validate, layer_opacity
from studio.rig import render_scene

class OpacityTest(unittest.TestCase):
 def setUp(self):
  self.p=new_project('Blink',64,64)
  self.l=mesh_layer('Iris','iris.png',(0,0,64,64),1)
  self.p['layers']=[self.l]
  self.l['opacity_keys']={'ParamEyeLOpen':[{'value':0,'opacity':0},{'value':.1,'opacity':1},{'value':1,'opacity':1}]}
 def test_interpolation_independence_and_javascript_parity(self):
  for eye in [0,.05,.1,.5,1]:
   next(q for q in self.p['parameters'] if q['id']=='ParamEyeLOpen')['value']=eye
   next(q for q in self.p['parameters'] if q['id']=='ParamEyeROpen')['value']=0
   expected=min(1,eye*10)
   self.assertAlmostEqual(layer_opacity(self.l,self.p['parameters']),expected)
   js="const R=require('./web/rig.js');const p=JSON.parse(process.argv[1]);console.log(R.opacity(p.layers[0],p.parameters))"
   self.assertAlmostEqual(float(subprocess.check_output(['node','-e',js,json.dumps(self.p)])),expected)
 def test_factors_compose_and_mask_export_uses_opacity(self):
  mask=mesh_layer('Mask','mask.png',(0,0,64,64),1)
  mask.update(mask_only=True,opacity_keys=self.l['opacity_keys'])
  self.l['masks']=[mask['id']];self.p['layers'].append(mask)
  next(q for q in self.p['parameters'] if q['id']=='ParamEyeLOpen')['value']=.05
  validate(self.p)
  im,_=render_scene(self.p,{'iris.png':Image.new('RGBA',(64,64),'red'),'mask.png':Image.new('RGBA',(64,64),'white')})
  self.assertEqual(im.getpixel((20,20))[3],64)
 def test_invalid_opacity_keys_rejected(self):
  for keys in [{'Unknown':[]},{'ParamEyeLOpen':[{'value':0,'opacity':2}]},{'ParamEyeLOpen':[{'value':0,'opacity':0}]*2}]:
   self.l['opacity_keys']=keys
   with self.assertRaises(ValueError):validate(self.p)
 def test_missing_default_is_one_and_legacy_unchanged(self):
  self.l['opacity']=.4;self.l['opacity_keys']={}
  self.assertEqual(layer_opacity(self.l,self.p['parameters']),.4)
  self.l['opacity_keys']={'ParamEyeLOpen':[{'value':0,'opacity':0}]}
  self.assertEqual(layer_opacity(self.l,self.p['parameters']),.4)
