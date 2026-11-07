import copy
import json
import math
import subprocess
import tempfile
import unittest
from PIL import Image
from studio.model import new_project, mesh_layer, validate
from studio.rig import local_vertices, world_vertices
from studio.storage import Store, RevisionConflict


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.p = new_project('Editor',64,64)
        self.p['deformers'] = []
        self.l = mesh_layer('Part','part.png',(8,8,32,32),1)
        self.p['layers'] = [self.l]

    def js(self, source, data=None):
        pre = "const R=require('./web/rig.js'),E=require('./web/editor-ops.js'),p=JSON.parse(process.argv[1]);"
        return json.loads(subprocess.check_output(['node','-e',pre+source,json.dumps(data or self.p)]))

    def test_polar_rotation_preserves_scale_and_matches_export(self):
        d = dict(id='r',name='R',type='rotation',rotation_mode='polar',vertices=[[0,0],[10,0]],rest=[[0,0],[10,0]],keys={'ParamAngleX':[dict(value=30,delta=[[0,0],[-10,10]])]})
        self.p['deformers']=[d];self.l['parent']='r'
        for value in [0,7.5,15,22.5,30]:
            self.p['parameters'][0]['value']=value
            a,b=local_vertices(d,self.p['parameters'])
            self.assertAlmostEqual(math.dist(a,b),10)
            actual=self.js('console.log(JSON.stringify(R.world(p.layers[0],p)))')
            expected=world_vertices(self.l,self.p)
            for v,w in zip(actual,expected):
                for x,y in zip(v,w):self.assertAlmostEqual(x,y)
        validate(self.p)

    def test_existing_rotation_stays_legacy_until_enabled(self):
        d=dict(type='rotation',vertices=[[0,0],[10,0]],keys={'ParamAngleX':[dict(value=30,delta=[[0,0],[-10,10]])]})
        self.p['parameters'][0]['value']=15
        self.assertEqual(local_vertices(d,self.p['parameters']),[[0,0],[5,5]])

    def test_reparent_preserves_world_and_export_with_bind(self):
        result=self.js("const a=R.deformer('rotation','A',[0,0,40,40]),b=R.deformer('rotation','B',[0,0,30,30]);a.id='a';b.id='b';a.vertices=[[10,20],[10,40]];b.vertices=[[30,5],[15,5]];p.deformers=[a,b];p.layers[0].parent='a';const before=R.world(p.layers[0],p);E.reparent(p,p.layers[0].id,'b');console.log(JSON.stringify({before,after:R.world(p.layers[0],p),project:p}));")
        validate(result['project'])
        exported=world_vertices(result['project']['layers'][0],result['project'])
        for expected,actual,cpu in zip(result['before'],result['after'],exported):
            for x,y,z in zip(expected,actual,cpu):self.assertAlmostEqual(x,y);self.assertAlmostEqual(x,z)

    def test_non_affine_reparent_is_rejected_without_mutation(self):
        out=self.js("const a=R.deformer('warp','A',[0,0,64,64]);a.id='a';a.vertices[4][0]+=10;p.deformers=[a];p.layers[0].parent='a';const before=JSON.stringify(p);let error;try{E.reparent(p,p.layers[0].id,null)}catch(e){error=e.message}console.log(JSON.stringify({error,same:before===JSON.stringify(p)}));")
        self.assertTrue(out['same']);self.assertIn('изогнут',out['error'])

    def test_exclusive_mask_follows_reparent(self):
        out=self.js("const a=R.deformer('rotation','A',[0,0,64,64]);a.id='a';a.vertices[0][0]+=8;a.vertices[1][0]+=8;p.deformers=[a];const n=p.layers[0],m=JSON.parse(JSON.stringify(n));m.id='mask';m.mask_only=true;m.parent='a';n.parent='a';n.masks=['mask'];p.layers.push(m);const before=R.world(m,p);E.reparent(p,n.id,null);console.log(JSON.stringify({before,after:R.world(m,p),parent:m.parent}));")
        self.assertIsNone(out['parent']);self.assertEqual(out['before'],out['after'])

    def test_refinement_preserves_keys_uv_and_combinations(self):
        self.l['keys']={'ParamAngleX':[dict(value=30,delta=[[0,0],[3,4],[2,6],[9,2]])]}
        self.l['combinations']=[dict(parameters=['ParamAngleX','ParamAngleY'],keys=[dict(values=[30,30],delta=[[2,3]]*4)])]
        out=self.js("const original=JSON.parse(JSON.stringify(p.layers[0]));const i=E.splitTriangle(p.layers[0],0);const q={...p,parameters:p.parameters.map(q=>({...q,value:q.max}))};console.log(JSON.stringify({project:p,index:i,expected:R.local(original,q.parameters).filter((v,j)=>original.triangles[0].includes(j)).reduce((a,v)=>a.map((x,k)=>x+v[k]/3),[0,0]),actual:R.local(p.layers[0],q.parameters)[i]}));")
        validate(out['project'])
        for x,y in zip(out['expected'],out['actual']):self.assertAlmostEqual(x,y)
        back=self.js("E.removeVertex(p.layers[0],4);console.log(JSON.stringify(p.layers[0]));",out['project'])
        self.assertEqual(back['vertices'],self.l['vertices']);self.assertEqual(back['uv'],self.l['uv']);self.assertEqual(back['keys'],self.l['keys'])

    def test_refine_warp_preserves_surface(self):
        out=self.js("const d=R.deformer('warp','A',[0,0,64,64]);d.vertices[4][0]+=10;d.keys.ParamAngleX=[{value:30,delta:d.vertices.map((v,i)=>[i,2*i])}];p.parameters[0].value=14;const points=[[5,9],[31,29],[63,54]],before=points.map(v=>R.transform(d,v,p.parameters));E.refineWarp(d);console.log(JSON.stringify({before,after:points.map(v=>R.transform(d,v,p.parameters))}));")
        for a,b in zip(out['before'],out['after']):
            for x,y in zip(a,b):self.assertAlmostEqual(x,y)

    def test_stale_save_blocked_and_current_save_survives(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);self.l['asset']=store.put_image(Image.new('RGBA',(8,8),'white'));store.save(self.p)
            a=store.load(self.p['id']);b=store.load(self.p['id']);a['name']='Updated';store.save(a)
            b['duration']=9
            with self.assertRaises(RevisionConflict):store.save(b)
            self.assertEqual(store.load(a['id'])['name'],'Updated')
            a['duration']=7;store.save(a);self.assertEqual(a['_revision'],3)

    def test_degenerate_indices_rejected(self):
        self.l['triangles']=[[0,0,0]]
        with self.assertRaisesRegex(ValueError,'треугольники'):validate(self.p)

    def test_compiled_frame_matches_direct_geometry(self):
        out=self.js("const d=R.deformer('warp','warp',[0,0,64,64]);d.id='warp';d.vertices[4][0]+=7;d.bind=[1,.1,.2,1,4,8];p.deformers=[d];p.layers[0].parent=d.id;p.layers[0].bind=[1,0,0,1,5,0];console.log(JSON.stringify([R.world(p.layers[0],p),R.evaluator(p)(p.layers[0])]));")
        self.assertEqual(out[0],out[1])

    def test_compositor_shared_nested_masks_and_pool_reuse(self):
        # An alpha-only canvas double verifies the compositing graph and buffer lifetime.
        code="""
        const fs=require('fs'),vm=require('vm');
        const document={createElement(){const c={width:0,height:0,alpha:0};const ctx={globalCompositeOperation:'source-over',clearRect(){c.alpha=0},drawImage(src){const a=src.alpha;if(this.globalCompositeOperation==='destination-in')c.alpha*=a;else if(this.globalCompositeOperation==='destination-out')c.alpha*=1-a;else c.alpha=a+c.alpha*(1-a);}};c.getContext=()=>ctx;return c;}};
        const sandbox={document,Rig:R};vm.createContext(sandbox);vm.runInContext(fs.readFileSync('./web/renderer.js','utf8')+';this.Renderer=SceneRenderer;',sandbox);
        const scene=new sandbox.Renderer();scene.mesh={render(p){let alpha=0;for(const l of p.layers)alpha=l.opacity+alpha*(1-l.opacity);return {alpha};}};
        p.layers=[{id:'m',visible:false,mask_only:true,opacity:.5},{id:'n',visible:false,mask_only:true,opacity:.8,masks:['m']},{id:'a',visible:true,opacity:.6,masks:['n']},{id:'b',visible:true,opacity:.7,masks:['m'],mask_invert:true}];
        const alpha=scene.render(p,new Map(),()=>[]).alpha,count=scene.surfaces.length;
        const second=scene.render(p,new Map(),()=>[]).alpha;
        console.log(JSON.stringify({alpha,second,count,after:scene.surfaces.length}));
        """
        out=self.js(code)
        self.assertAlmostEqual(out['alpha'],.35+.24*(1-.35))
        self.assertEqual(out['alpha'],out['second']);self.assertEqual(out['count'],out['after'])
        self.assertLessEqual(out['count'],5)

    def test_old_project_migrates_only_on_save(self):
        self.p['format']='l2d-ai-studio/1';validate(self.p)
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);self.l['asset']=store.put_image(Image.new('RGBA',(8,8),'white'))
            store.save(self.p)
            self.assertEqual(self.p['format'],'l2d-ai-studio/2')
            self.assertEqual(store.load(self.p['id'])['layers'],self.p['layers'])

if __name__=='__main__':unittest.main()
