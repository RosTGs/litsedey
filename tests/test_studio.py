import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from PIL import Image, ImageDraw
from psd_tools import PSDImage

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import App, Handler, ThreadingHTTPServer
from studio.model import new_project, mesh_layer, validate, deform, render_layer, motion, expression
from studio.storage import Store, atomic_json
from studio import providers

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.p=new_project('Test',64,64)
        self.l=mesh_layer('Part','a.png',(0,0,64,64),2)
        self.p['layers']=[self.l]

    def test_interpolation_implicit_neutral_and_additive(self):
        self.l['keys']['ParamAngleX']=[dict(value=30,delta=[[20,0]]*9)]
        self.l['keys']['ParamAngleY']=[dict(value=-30,delta=[[0,-8]]*9)]
        self.p['parameters'][0]['value']=15
        self.p['parameters'][1]['value']=-15
        result=deform(self.l,self.p['parameters'])
        self.assertEqual(result[0],[10,-4])
        self.assertEqual(result[-1],[74,60])

    def test_validation_rejects_bad_indices_and_nonfinite(self):
        self.l['triangles'][0][0]=1000
        with self.assertRaises(ValueError):validate(self.p)
        self.l['triangles'][0][0]=0
        self.l['vertices'][0][0]=float('nan')
        with self.assertRaises(ValueError):validate(self.p)

    def test_duplicate_keys_rejected(self):
        k=dict(value=30,delta=[[1,1]]*9)
        self.l['keys']['ParamAngleX']=[k,k]
        with self.assertRaises(ValueError):validate(self.p)

    def test_texture_and_alpha_survive_mesh_rasterization(self):
        im=Image.new('RGBA',(64,64))
        ImageDraw.Draw(im).rectangle((10,10,53,53),fill=(240,50,90,180))
        output=render_layer(self.l,im,(64,64),self.p['parameters'])
        # Pillow's premultiplied bicubic resampling may round color by one unit.
        self.assertTrue(all(abs(a-b)<=1 for a,b in zip(output.getpixel((32,32)),(240,50,90,180))))
        self.assertEqual(output.getpixel((2,2))[3],0)
        self.assertEqual(output.getbbox(),im.getbbox())

    def test_motion_totals_time_order_and_boundary_extension(self):
        values={q['id']:q['default'] for q in self.p['parameters']}
        self.p['timeline']=[dict(time=2,values=dict(values,ParamAngleX=30)),dict(time=1,values=values)]
        m=motion(self.p)
        self.assertEqual(m['Meta']['TotalSegmentCount'],21)
        self.assertEqual(m['Meta']['TotalPointCount'],28)
        self.assertEqual(m['Curves'][0]['Segments'],[0,0,0,1,0,0,2,30,0,3,30])
        self.assertEqual(expression(self.p)['Parameters'][0]['Blend'],'Overwrite')

    def test_empty_motion_fails(self):
        with self.assertRaises(ValueError):motion(self.p)

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(self.temp.name)
        self.p=new_project('Test',64,64)
        im=Image.new('RGBA',(64,64));ImageDraw.Draw(im).ellipse((10,10,50,50),fill=(50,200,90,190))
        self.store.add_image(self.p,im,'Part')
        self.store.save(self.p)
    def tearDown(self):self.temp.cleanup()

    def test_bundle_roundtrip_preserves_mesh_keys_and_pixels(self):
        self.p['layers'][0]['keys']['ParamAngleX']=[dict(value=30,delta=[[3,4]]*25)]
        result=self.store.export(self.p,'bundle')
        restored=self.store.import_bundle(self.store.path('exports',result['file']).read_bytes())
        self.assertNotEqual(restored['id'],self.p['id'])
        self.assertEqual(restored['layers'][0]['keys'],self.p['layers'][0]['keys'])
        self.assertEqual(restored['layers'][0]['vertices'],self.p['layers'][0]['vertices'])
        self.assertEqual(self.store.path('assets',restored['layers'][0]['asset']).read_bytes(),self.store.path('assets',self.p['layers'][0]['asset']).read_bytes())

    def test_psd_roundtrip_rgb_depth_alpha_and_layer_placement(self):
        self.p['layers'][0]['name']='Голова · 漫画'
        result=self.store.export(self.p,'psd');file=self.store.path('exports',result['file'])
        psd=PSDImage.open(file)
        self.assertEqual(psd.depth,8);self.assertEqual(psd.color_mode.name,'RGB')
        self.assertEqual(len(psd),1)
        self.assertEqual(psd[0].name,'Голова · 漫画')
        alpha=psd[0].topil().getchannel('A')
        self.assertEqual(alpha.getextrema(),(0,190))
        self.assertEqual(alpha.getbbox(),(10,10,51,51))
        imported=self.store.import_psd(file.read_bytes(),'Reimport')['project']
        self.assertEqual(imported['layers'][0]['vertices'][0],[10,10])
        self.assertEqual(imported['layers'][0]['vertices'][-1],[51,51])

    def test_path_traversal_and_symlink_are_blocked(self):
        with self.assertRaises(ValueError):self.store.path('assets','../settings.json')
        (self.store.root/'assets/escape.png').symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):self.store.path('assets','escape.png')

    def test_interrupted_job_not_retried(self):
        atomic_json(self.store.path('jobs','test.json'),dict(id='test',status='running',remote_id='remote'))
        restarted=Store(self.store.root)
        job=json.loads(restarted.path('jobs','test.json').read_text())
        self.assertEqual(job['status'],'interrupted');self.assertEqual(job['remote_id'],'remote')

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.app=App(root/'data',root/'settings.json')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.app=self.app
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.app.pool.shutdown();self.temp.cleanup()
    def call(self,path,data=None,headers=None):
        h={'Content-Type':'application/json','X-Studio-Token':self.app.token};h.update(headers or {})
        request=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=h)
        return urllib.request.urlopen(request)

    def test_cross_origin_and_bad_token_block_mutations(self):
        for headers in ({'X-Studio-Token':'bad'},{'Origin':'https://evil.example'},{'Host':'evil.example'}):
            with self.assertRaises(urllib.error.HTTPError) as cm:self.call('/api/create',{},headers)
            self.assertEqual(cm.exception.code,403)
        self.assertEqual(self.app.store.list(),[])

    def test_exports_download_as_json_bytes_and_config_redacted(self):
        self.call('/api/settings',{'fal_key':'private-test-key'})
        data=self.call('/api/bootstrap').read()
        self.assertNotIn(b'private-test-key',data)
        self.assertEqual(self.app.config_path.stat().st_mode&0o777,0o600)
        p=json.load(self.call('/api/create',{'name':'test'}))
        result=json.load(self.call('/api/export',{'project_id':p['id'],'kind':'expression'}))
        downloaded=json.load(self.call(result['url']))
        self.assertEqual(downloaded['Type'],'Live2D Expression')

    def test_conflict_returns_409_and_save_copy_keeps_both(self):
        p=json.load(self.call('/api/create',{'name':'version test'}))
        stale=copy.deepcopy(p);p['name']='new version'
        saved=json.load(self.call('/api/save',{'project':p}))
        with self.assertRaises(urllib.error.HTTPError) as cm:self.call('/api/save',{'project':stale})
        self.assertEqual(cm.exception.code,409)
        self.assertEqual(json.load(cm.exception)['code'],'revision_conflict')
        copied=json.load(self.call('/api/save-copy',{'project':stale}))
        self.assertNotEqual(saved['id'],copied['id'])
        self.assertEqual(self.app.store.load(saved['id'])['name'],'new version')

class ProviderTests(unittest.TestCase):
    def test_fal_queue_id_persisted_before_results(self):
        events=[]
        responses=[dict(request_id='r1',status_url='https://queue.fal.run/a/status',response_url='https://queue.fal.run/a/result'),dict(status='COMPLETED'),dict(images=[{'url':'https://v3.fal.media/test.png'}]),b'PNG']
        with patch.object(providers,'request',side_effect=responses) as req:
            result=list(providers.generate({'fal_key':'test'},{'provider':'fal','prompt':'test'},None,lambda **kw:events.append(kw)))
        self.assertEqual(result,[b'PNG']);self.assertEqual(events[0]['remote_id'],'r1')
        self.assertEqual(req.call_count,4)

    def test_comfy_api_workflow_and_output(self):
        workflow={'1':{'class_type':'SaveImage','inputs':{}}}
        outputs={'p1':{'status':{'completed':True},'outputs':{'1':{'images':[{'filename':'x.png','type':'output','subfolder':''}]}}}}
        with patch.object(providers,'request',side_effect=[{'prompt_id':'p1'},outputs,b'PNG']):
            result=list(providers.generate({'comfy_url':'http://127.0.0.1:8188'},{'provider':'comfy','workflow':workflow},None,lambda **kw:None))
        self.assertEqual(result,[b'PNG'])

    def test_untrusted_result_hosts_rejected(self):
        for url in ['http://127.0.0.1/private','https://fal.media.attacker.com/x','file:///etc/passwd']:
            with self.assertRaises(providers.ProviderError):providers.download_url(url)

if __name__=='__main__':unittest.main(verbosity=2)
