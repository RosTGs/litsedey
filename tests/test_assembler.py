import copy
import unittest
from studio.model import new_project,mesh_layer,layer_opacity,deform
from studio.assembler import analyze,plan,build

class AssemblerTest(unittest.TestCase):
 def setUp(self):
  self.p=new_project('Artwork',256,256);self.mapping={}
  for side in ['L','R']:
   for role,label in [('white','Белок'),('iris','Радужка'),('upper','Верхнее веко'),('lower','Нижнее веко'),('closed','Закрытый глаз')]:
    l=mesh_layer(label+' · '+('левый' if side=='L' else 'правый'),'a.png',(120 if side=='L' else 40,60,50,24),1)
    self.p['layers'].append(l);self.mapping[side+'.'+role]=l['id']
  self.recipe=dict(template='eyes-v1',mapping=self.mapping)
 def test_copy_build_blink_and_mask_independence(self):
  original=copy.deepcopy(self.p);p,r=build(self.p,self.recipe)
  self.assertEqual(self.p,original);self.assertNotEqual(p['id'],self.p['id']);self.assertTrue(r['ok'])
  by={l['id']:l for l in p['layers']}
  next(q for q in p['parameters'] if q['id']=='ParamEyeLOpen')['value']=0
  self.assertEqual(layer_opacity(by[self.mapping['L.white']],p['parameters']),0)
  self.assertEqual(layer_opacity(by[self.mapping['L.closed']],p['parameters']),1)
  self.assertEqual(layer_opacity(by[self.mapping['R.white']],p['parameters']),1)
  self.assertEqual(by[self.mapping['L.iris']]['masks'],[self.mapping['L.white']])
  self.assertNotEqual(deform(by[self.mapping['L.white']],p['parameters']),by[self.mapping['L.white']]['vertices'])
 def test_ambiguous_names_not_assigned(self):
  self.p['layers'].append(mesh_layer('Белок · левый','a.png',(0,0,20,20),1))
  r=analyze(self.p);self.assertIn('L.white',r['ambiguous']);self.assertNotIn('L.white',r['suggestions'])
 def test_missing_closed_and_reused_layers_block_build(self):
  self.mapping.pop('L.closed');self.mapping['R.iris']=self.mapping['L.iris']
  self.assertFalse(plan(self.p,self.recipe)['ok'])
  with self.assertRaises(ValueError):build(self.p,self.recipe)
 def test_incompatible_params_and_invalid_options(self):
  self.p['parameters'][3]['max']=2
  self.recipe['options']={'threshold':float('nan')}
  result=plan(self.p,self.recipe);self.assertFalse(result['ok']);self.assertGreaterEqual(len(result['errors']),2)
 def test_idempotent_recipe_has_no_accumulated_deformations(self):
  a,_=build(self.p,self.recipe);b,_=build(a,self.recipe)
  self.assertEqual(a['layers'],b['layers']);self.assertEqual(a['parameters'],b['parameters'])
