#!/usr/bin/env python3
"""Loopback-only desktop application server. Python 3.9+."""
from __future__ import annotations
import argparse
import base64
import concurrent.futures
import io
import json
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
from studio.model import new_project, uid
from studio.storage import Store, atomic_json, RevisionConflict
from studio import providers
from studio.demo import seed_demo
from studio.audit import audit
from studio import assembler

class App:
    def __init__(self, data, config):
        self.store = Store(data)
        self.config_path = Path(config)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = json.loads(self.config_path.read_text()) if self.config_path.exists() else {}
        self.config.setdefault('comfy_url', 'http://127.0.0.1:8188')
        self.token = secrets.token_urlsafe(32)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self.jobs_lock = threading.Lock()

    def public_config(self):
        return dict(fal_configured=bool(self.config.get('fal_key') or os.environ.get('FAL_KEY')),
                    comfy_url=self.config['comfy_url'])

    def settings(self, data):
        config = dict(self.config)
        url = str(data.get('comfy_url', config['comfy_url'])).rstrip('/')
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.username or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('ComfyUI: укажите локальный адрес, например http://127.0.0.1:8188')
        config.update(comfy_url=url)
        if data.get('fal_key'):
            key = str(data['fal_key']).strip()
            if len(key) > 1024 or '\n' in key or '\r' in key:
                raise ValueError('Некорректный ключ')
            config['fal_key'] = key
        if data.get('remove_fal_key'):
            config.pop('fal_key', None)
        atomic_json(self.config_path, config)
        self.config = config
        return self.public_config()

    def jobs(self):
        with self.jobs_lock:
            return [json.loads(p.read_text()) for p in sorted((self.store.root/'jobs').glob('*.json'),
                     key=lambda p:p.stat().st_mtime, reverse=True)]

    def generate(self, data):
        project = self.store.load(data['project_id'])
        spec = {k: data[k] for k in ('provider','prompt','endpoint','inputs','reference_field','workflow','checkpoint','seed') if k in data}
        if spec.get('provider') not in ('fal', 'comfy'):
            raise ValueError('Выберите fal или ComfyUI')
        if not isinstance(spec.get('prompt', ''), str) or len(spec.get('prompt', '')) > 12000:
            raise ValueError('Запрос: до 12 000 символов')
        if spec.get('inputs') is not None and not isinstance(spec['inputs'], dict):
            raise ValueError('Входные параметры должны быть JSON-объектом')
        config = dict(self.config)
        config['fal_key'] = config.get('fal_key') or os.environ.get('FAL_KEY', '')
        if spec['provider'] == 'fal' and not config['fal_key']:
            raise ValueError('Добавьте ключ fal в разделе «Подключения»')
        reference = None
        if data.get('reference_asset'):
            if data['reference_asset'] not in {x['asset'] for x in project['layers']}:
                raise ValueError('Референс должен быть слоем текущего проекта')
            reference = self.store.path('assets', data['reference_asset']).read_bytes()
        job = dict(id=uid(), project_id=project['id'], status='queued', created=time.time(), spec=spec,
                   reference_asset=data.get('reference_asset'), assets=[])
        with self.jobs_lock:
            if sum(j['status'] in ('queued','running') for j in self.jobs_unlocked()) >= 8:
                raise ValueError('В очереди уже 8 задач. Дождитесь завершения.')
            atomic_json(self.store.path('jobs', job['id']+'.json'), job)
        self.pool.submit(self.worker, job, config, reference)
        return job

    def jobs_unlocked(self):
        return [json.loads(p.read_text()) for p in (self.store.root/'jobs').glob('*.json')]

    def worker(self, job, config, reference):
        def update(**fields):
            job.update(fields)
            with self.jobs_lock:
                atomic_json(self.store.path('jobs',job['id']+'.json'),job)
        try:
            update(status='running')
            for raw in providers.generate(config, job['spec'], reference, update):
                image = self.store.image(raw)
                job['assets'].append(self.store.put_image(image))
                update(assets=job['assets'])
            update(status='completed')
        except Exception as exc:
            message = str(exc)
            if config.get('fal_key'):
                message = message.replace(config['fal_key'], '[скрыто]')
            update(status='failed', error=message[:600])

    def seed(self):
        if not self.store.list():
            seed_demo(self.store)

class Handler(BaseHTTPRequestHandler):
    server_version = 'Litsedey/0.4'
    def log_message(self, fmt, *args):
        pass

    @property
    def app(self):
        return self.server.app

    def guard(self, mutation=False):
        hosts = {'127.0.0.1:%d'%self.server.server_port,'localhost:%d'%self.server.server_port}
        if self.headers.get('Host') not in hosts:
            raise PermissionError('Недопустимый адрес сервера')
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://'+h for h in hosts}:
            raise PermissionError('Запрос из другого приложения заблокирован')
        if mutation and not secrets.compare_digest(self.headers.get('X-Studio-Token',''),self.app.token):
            raise PermissionError('Обновите окно приложения')

    def send(self, data, status=200, mime='application/json; charset=utf-8', attachment=None):
        body = data if isinstance(data, bytes) else json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if attachment:
            self.send_header('Content-Disposition','attachment; filename="'+attachment+'"')
        self.end_headers()
        self.wfile.write(body)

    def error(self, exc):
        if isinstance(exc, RevisionConflict):
            self.send({'error':str(exc),'code':'revision_conflict'},409)
        elif isinstance(exc, PermissionError):
            self.send({'error':str(exc)},403)
        elif isinstance(exc, FileNotFoundError):
            self.send({'error':'Файл или проект не найден'},404)
        elif isinstance(exc,(ValueError,KeyError,TypeError,OverflowError)):
            self.send({'error':str(exc)[:400]},400)
        else:
            self.send({'error':'Операция не выполнена: '+type(exc).__name__},500)

    def do_GET(self):
        try:
            self.guard()
            path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
            if path == '/api/bootstrap':
                return self.send(dict(app='kadr-ai-studio',token=self.app.token,projects=self.app.store.list(),settings=self.app.public_config(),jobs=self.app.jobs()))
            if path == '/api/jobs':
                return self.send(self.app.jobs())
            if path.startswith('/api/projects/'):
                return self.send(self.app.store.load(path.split('/')[-1]))
            for category in ('assets','exports'):
                if path.startswith('/'+category+'/'):
                    file = self.app.store.path(category,path[len(category)+2:])
                    return self.send(file.read_bytes(),mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream',
                                     attachment=file.name if category=='exports' else None)
            files = {'/':'index.html','/app.js':'app.js','/renderer.js':'renderer.js','/rig.js':'rig.js','/rig-ui.js':'rig-ui.js','/style.css':'style.css','/fonts/InterVariable.woff2':'fonts/InterVariable.woff2'}
            for name in ('capture.js', 'capture-map.js', 'capture-worker.js', 'assembly.js', 'editor-ops.js', 'editor-ui.js'):
                files['/'+name] = name
            vendor_names = ('vision_bundle.cjs', 'face_landmarker.task', 'wasm/vision_wasm_internal.js', 'wasm/vision_wasm_internal.wasm', 'wasm/vision_wasm_nosimd_internal.js', 'wasm/vision_wasm_nosimd_internal.wasm', 'wasm/vision_wasm_module_internal.js', 'wasm/vision_wasm_module_internal.wasm')
            for name in vendor_names:
                files['/vendor/mediapipe/'+name] = 'vendor/mediapipe/'+name
            if path not in files:
                raise FileNotFoundError()
            file = ROOT/'web'/files[path]
            self.send(file.read_bytes(),mime='application/javascript' if file.suffix == '.cjs' else mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
        except Exception as exc:
            self.error(exc)

    def do_POST(self):
        try:
            self.guard(True)
            if 'application/json' not in self.headers.get('Content-Type',''):
                raise ValueError('Ожидается application/json')
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= 90*1024*1024:
                raise ValueError('Размер запроса должен быть меньше 90 МБ')
            data = json.loads(self.rfile.read(size), parse_constant=lambda s: (_ for _ in ()).throw(ValueError('Некорректное число')))
            if not isinstance(data,dict):
                raise ValueError('Ожидается JSON-объект')
            path = self.path
            store = self.app.store
            if path == '/api/create':
                result = store.save(new_project(str(data.get('name','Новый персонаж')),int(data.get('width',1024)),int(data.get('height',1536))))
            elif path in ('/api/assembly/analyze','/api/assembly/plan','/api/assembly/build'):
                source=store.load(data['project_id'])
                if path.endswith('/analyze'):
                    result=assembler.analyze(source)
                elif path.endswith('/plan'):
                    result=assembler.plan(source,data['recipe'])
                else:
                    project,report=assembler.build(source,data['recipe'])
                    result=dict(project=store.save(project),report=report)
            elif path == '/api/save':
                result = store.save(data['project'])
            elif path == '/api/save-copy':
                project = data['project']
                project['id'] = uid()
                project['name'] = (project['name'] + ' · копия')[:120]
                project.pop('_revision', None)
                result = store.save(project)
            elif path == '/api/import':
                raw = base64.b64decode(data['content'],validate=True)
                name = str(data['name'])
                if name.lower().endswith('.zip'):
                    result = dict(project=store.import_bundle(raw),warnings=[])
                elif name.lower().endswith('.psd'):
                    result = store.import_psd(raw,Path(name).stem[:120])
                else:
                    project = store.load(data['project_id'])
                    result = dict(project=store.save(store.add_image(project,store.image(raw),Path(name).stem)),warnings=[])
            elif path == '/api/replace-asset':
                project = store.load(data['project_id'])
                if project.get('_revision',0) != data.get('revision',0):
                    raise RevisionConflict('Рисунок не заменён: проект уже изменён в другом окне.')
                layer = next(l for l in project['layers'] if l['id'] == data['layer_id'])
                raw = base64.b64decode(data['content'],validate=True)
                layer['asset'] = store.put_image(store.image(raw))
                result = store.save(project)
            elif path == '/api/export':
                result = store.export(store.load(data['project_id']),data['kind'])
            elif path == '/api/settings':
                result = self.app.settings(data)
            elif path == '/api/generate':
                result = self.app.generate(data)
            elif path == '/api/add-generated':
                job = json.loads(store.path('jobs',data['job_id']+'.json').read_text())
                asset = data['asset']
                if asset not in job['assets']:
                    raise ValueError('Результат не найден')
                p = store.load(data['project_id'])
                result = store.save(store.add_image(p,store.image(store.path('assets',asset).read_bytes()),'AI · '+job['spec'].get('prompt','Изображение')[:60]))
            elif path == '/api/check-comfy':
                stats=providers.request(self.app.config['comfy_url']+'/system_stats',timeout=3)
                result=dict(connected=True,system=stats.get('system',{}))
            elif path == '/api/open-export':
                file=store.path('exports',data['file'])
                if not file.is_file():
                    raise FileNotFoundError()
                subprocess.run(['open','-R',str(file)],check=True)
                result=dict(ok=True)
            elif path == '/api/audit':
                file=store.path('exports',data['file'])
                result=audit(file)
            else:
                raise FileNotFoundError()
            self.send(result)
        except Exception as exc:
            self.error(exc)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=18321)
    parser.add_argument('--data',default=str(ROOT/'data'))
    parser.add_argument('--config',default=str(ROOT/'data/settings.json'))
    parser.add_argument('--no-seed',action='store_true')
    args=parser.parse_args()
    app=App(args.data,args.config)
    if not args.no_seed:
        app.seed()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.app=app
    print('Лицедей: http://127.0.0.1:%d'%server.server_port,flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.pool.shutdown(wait=False,cancel_futures=True)

if __name__=='__main__':
    main()
