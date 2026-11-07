import copy
import json
import math
import subprocess
import unittest
from PIL import Image
from studio.model import new_project, mesh_layer, validate, motion
from studio.rig import world_vertices, render_scene, sample_track, physics_frames, bake_physics


def deformer(kind, name, parent=None):
    d=dict(id=name, name=name, parent=parent, type=kind, keys={})
    if kind == 'rotation':
        d.update(vertices=[[16,16],[32,16]],rest=[[16,16],[32,16]])
    else:
        d.update(bounds=[0,0,32,32],divisions=1,vertices=[[0,0],[32,0],[0,32],[32,32]])
    return d


class RigTest(unittest.TestCase):
    def setUp(self):
        self.p=new_project('Rig test',64,64)
        self.l=mesh_layer('Paint','paint.png',(16,16,16,16),size=1)
        self.p['layers']=[self.l]
        self.p['deformers']=[]

    def test_nested_rotation_and_warp_matches_javascript(self):
        r=deformer('rotation','rot')
        r['vertices'][1]=[16,32]
        w=deformer('warp','warp','rot')
        w['vertices']=[[x+10,y] for x,y in w['vertices']]
        self.p['deformers']=[r,w];self.l['parent']='warp'
        validate(self.p)
        vs=world_vertices(self.l,self.p)
        self.assertAlmostEqual(vs[0][0],16)
        self.assertAlmostEqual(vs[0][1],26)
        js="const R=require('./web/rig.js');const p=JSON.parse(process.argv[1]);console.log(JSON.stringify(R.world(p.layers[0],p)))"
        actual=json.loads(subprocess.check_output(['node','-e',js,json.dumps(self.p)]))
        for a,b in zip(actual,vs):
            for x,y in zip(a,b):self.assertAlmostEqual(x,y)

    def test_inverse_interaction_under_rotated_warp(self):
        r=deformer('rotation','r');r['vertices'][1]=[25,29]
        w=deformer('warp','w','r');w['vertices'][3]=[40,45]
        self.p['deformers']=[r,w];self.l['parent']='w'
        js="const R=require('./web/rig.js');const p=JSON.parse(process.argv[1]);const n=p.layers[0];console.log(JSON.stringify(R.toLocal(n,R.toWorld(n,[23,21],p),p)))"
        actual=json.loads(subprocess.check_output(['node','-e',js,json.dumps(self.p)]))
        self.assertAlmostEqual(actual[0],23,places=3)
        self.assertAlmostEqual(actual[1],21,places=3)

    def test_hierarchy_and_mask_cycles_rejected(self):
        a=deformer('warp','a','b');b=deformer('warp','b','a');self.p['deformers']=[a,b]
        with self.assertRaisesRegex(ValueError,'Цикл'):validate(self.p)
        self.p['deformers']=[]
        m=mesh_layer('Mask','mask.png',(0,0,32,32),1);self.p['layers'].append(m)
        self.l['masks']=[m['id']];m['masks']=[self.l['id']]
        with self.assertRaisesRegex(ValueError,'Цикл'):validate(self.p)

    def test_mask_alpha_hidden_source_and_inversion(self):
        m=mesh_layer('Mask','mask.png',(16,16,8,16),1)
        m.update(visible=False, mask_only=True)
        self.l['masks']=[m['id']];self.p['layers'].append(m)
        images={'paint.png':Image.new('RGBA',(16,16),(255,0,0,255)),'mask.png':Image.new('RGBA',(8,16),(0,0,0,128))}
        validate(self.p)
        im,_=render_scene(self.p,images)
        self.assertEqual(im.getpixel((20,20))[3],128)
        self.assertEqual(im.getpixel((29,20))[3],0)
        self.l['mask_invert']=True
        im,_=render_scene(self.p,images)
        self.assertEqual(im.getpixel((20,20))[3],127)
        self.assertEqual(im.getpixel((29,20))[3],255)

    def test_keyed_parent_moves_children(self):
        d=deformer('warp','d');self.p['deformers']=[d];self.l['parent']='d'
        q=self.p['parameters'][0];q['value']=15
        d['keys'][q['id']]=[dict(value=30,delta=[[8,0]]*4)]
        self.assertEqual(world_vertices(self.l,self.p)[0],[20,16])
        validate(self.p)

    def test_sparse_tracks_easing_export_and_counts(self):
        keys=[dict(time=0,value=-30,interpolation='smooth'),dict(time=1,value=30,interpolation='step'),dict(time=2,value=0,interpolation='linear')]
        self.p['tracks']={'ParamAngleX':keys};self.p['loop']=False
        self.assertAlmostEqual(sample_track(keys,.25,0),-20.625)
        self.assertEqual(sample_track(keys,1.9,0),30)
        self.assertEqual(sample_track(keys,2,0),0)
        m=motion(self.p)
        self.assertEqual(m['Meta']['CurveCount'],1)
        self.assertEqual(m['Meta']['TotalSegmentCount'],3)
        self.assertEqual(m['Meta']['TotalPointCount'],6)
        self.assertFalse(m['Meta']['Loop'])
        self.assertEqual(m['Curves'][0]['Segments'][2],1)
        self.assertEqual(m['Curves'][0]['Segments'][9],2)
        js="const R=require('./web/rig.js');const keys=JSON.parse(process.argv[1]);console.log(JSON.stringify([.25,1.9,2].map(t=>R.sample(keys,t,0))))"
        self.assertEqual(json.loads(subprocess.check_output(['node','-e',js,json.dumps(keys)])),[-20.625,30,0])

    def test_invalid_tracks_and_malformed_deformers(self):
        self.p['tracks']={'Bad':[]}
        with self.assertRaises(ValueError):validate(self.p)
        self.p['tracks']={'ParamAngleX':[dict(time=0,value=float('nan'))]}
        with self.assertRaises(ValueError):validate(self.p)
        self.p['tracks']={};self.p['deformers']=[deformer('warp','a')];self.p['deformers'][0]['divisions']=0
        with self.assertRaises(ValueError):validate(self.p)

    def test_physics_preview_matches_bake_and_settles(self):
        self.p['duration']=5
        self.p['tracks']={'ParamAngleX':[dict(time=0,value=30)]}
        self.p['physics']=[dict(id='spring',name='Spring',input='ParamAngleX',output='ParamAngleZ',frequency=2,damping=.4,strength=.5,enabled=True)]
        validate(self.p)
        times=[i/30 for i in range(151)]
        frames=list(physics_frames(self.p,times))
        self.assertEqual(frames[0]['ParamAngleZ'],0)
        self.assertAlmostEqual(frames[-1]['ParamAngleZ'],15,places=5)
        self.assertGreater(max(f['ParamAngleZ'] for f in frames),15)
        js="const R=require('./web/rig.js');const p=JSON.parse(process.argv[1]),s=new R.PhysicsPreview(p);console.log(JSON.stringify([0,.5,1,5].map(t=>s.apply({ParamAngleZ:0},t).ParamAngleZ)))"
        values=json.loads(subprocess.check_output(['node','-e',js,json.dumps(self.p)]))
        for actual,i in zip(values,[0,15,30,150]):self.assertAlmostEqual(actual,frames[i]['ParamAngleZ'],places=5)
        fractional=list(physics_frames(self.p,[.04,.08,.12]))
        js2=js.replace('[0,.5,1,5]','[.04,.08,.12]')
        for actual,expected in zip(json.loads(subprocess.check_output(['node','-e',js2,json.dumps(self.p)])),fractional):
            self.assertAlmostEqual(actual,expected['ParamAngleZ'],places=8)
        baked=bake_physics(self.p)
        curve=next(c for c in baked['Curves'] if c['Id']=='ParamAngleZ')
        self.assertAlmostEqual(curve['Segments'][-1],15,places=5)
        self.assertEqual(baked['Meta']['TotalSegmentCount'],300)

    def test_export_bundle_preserves_rig_and_masks(self):
        import tempfile
        from studio.storage import Store
        with tempfile.TemporaryDirectory() as root:
            store=Store(root)
            self.l['asset']=store.put_image(Image.new('RGBA',(16,16),(255,0,0,255)))
            self.p['deformers']=[deformer('warp','d')];self.l['parent']='d'
            self.l['mask_only']=True
            store.save(self.p)
            result=store.export(self.p,'bundle')
            back=store.import_bundle(store.path('exports',result['file']).read_bytes())
            self.assertEqual(back['deformers'],self.p['deformers'])
            self.assertEqual(back['layers'][0]['parent'],'d')
            self.assertTrue(back['layers'][0]['mask_only'])

    def test_combination_correction_blends_and_matches_javascript(self):
        self.l['combinations']=[dict(parameters=['ParamAngleX','ParamAngleY'],keys=[dict(values=[30,30],delta=[[12,8]]*4)])]
        self.p['parameters'][0]['value']=15;self.p['parameters'][1]['value']=15
        validate(self.p)
        vs=world_vertices(self.l,self.p)
        self.assertEqual(vs[0],[19,18])
        js="const R=require('./web/rig.js');const p=JSON.parse(process.argv[1]);console.log(JSON.stringify(R.world(p.layers[0],p)))"
        self.assertEqual(json.loads(subprocess.check_output(['node','-e',js,json.dumps(self.p)])),vs)
        self.p['parameters'][1]['value']=0
        self.assertEqual(world_vertices(self.l,self.p)[0],[16,16])
        self.l['combinations'].append(copy.deepcopy(self.l['combinations'][0]))
        with self.assertRaisesRegex(ValueError,'Повтор'):validate(self.p)

    def test_old_project_migration_keeps_animation(self):
        self.p['timeline']=[dict(time=0,values={q['id']:q['default'] for q in self.p['parameters']})]
        js="const R=require('./web/rig.js');console.log(JSON.stringify(R.normalize(JSON.parse(process.argv[1]))))"
        migrated=json.loads(subprocess.check_output(['node','-e',js,json.dumps(self.p)]))
        self.assertEqual(migrated['tracks']['ParamEyeLOpen'][0]['value'],1)
        self.assertEqual(migrated['timeline'],[])
        validate(migrated)

if __name__=='__main__':unittest.main()
