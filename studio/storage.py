from __future__ import annotations
import copy
import io
import json
import os
import threading
import zipfile
from pathlib import Path
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
from .rig import render_scene, bake_physics
from .model import FORMAT, new_project, mesh_layer, uid, validate, render_layer, expression, motion, layer_opacity

Image.MAX_IMAGE_PIXELS = 4096 * 4096

class RevisionConflict(ValueError):
    """A newer document exists; the caller must keep its changes as a copy."""

def atomic_json(path, value):
    temp = path.with_name(path.name + '.' + uid() + '.tmp')
    try:
        with open(temp, 'x', encoding='utf-8') as f:
            os.chmod(temp, 0o600)
            json.dump(value, f, ensure_ascii=False, allow_nan=False)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        for name in ('projects', 'assets', 'exports', 'jobs', 'backups'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        # An interrupted remote job must not be silently resubmitted (possible double billing).
        for path in (self.root / 'jobs').glob('*.json'):
            job = json.loads(path.read_text())
            if job['status'] in ('queued', 'running'):
                job.update(status='interrupted', error='Приложение было закрыто. Запрос автоматически не повторён; ID провайдера сохранён.')
                atomic_json(path, job)

    def path(self, category, name):
        if category not in ('projects', 'assets', 'exports', 'jobs') or not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..') or '\\' in name:
            raise ValueError('Недопустимый путь')
        path = (self.root / category / name).resolve()
        if path.parent != self.root / category:
            raise ValueError('Путь выходит за пределы проекта')
        return path

    def load(self, project_id):
        p = json.loads(self.path('projects', project_id + '.json').read_text())
        p.setdefault('_revision', 0)
        return p

    def save(self, project):
        validate(project)
        for layer in project['layers']:
            if not self.path('assets', layer['asset']).is_file():
                raise ValueError('Не найдено изображение слоя ' + layer['name'])
        with self.lock:
            path = self.path('projects', project['id'] + '.json')
            previous = json.loads(path.read_text()) if path.exists() else None
            revision = previous.get('_revision', 0) if previous else 0
            if previous and project.get('_revision', 0) != revision:
                raise RevisionConflict('Проект изменён в другом окне. Сохраните свои изменения отдельной копией.')
            saved = copy.deepcopy(project)
            saved['format'] = FORMAT
            saved['_revision'] = revision + 1
            if previous and previous.get('format') == 'l2d-ai-studio/1':
                backup = self.root / 'backups' / (project['id'] + '-before-v2.json')
                if not backup.exists():
                    atomic_json(backup, previous)
            atomic_json(path, saved)
            project['_revision'] = saved['_revision']
            project['format'] = FORMAT
        return project

    def list(self):
        result = []
        for path in sorted((self.root / 'projects').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            p = json.loads(path.read_text())
            result.append(dict(id=p['id'], name=p['name'], width=p['width'], height=p['height'], layers=len(p['layers'])))
        return result

    def image(self, raw):
        im = Image.open(io.BytesIO(raw))
        if im.width > 4096 or im.height > 4096:
            raise ValueError('Максимальный размер изображения — 4096 × 4096')
        im.load()
        return im.convert('RGBA')

    def put_image(self, image):
        name = uid() + '.png'
        image.save(self.path('assets', name))
        return name

    def add_image(self, p, image, name, position=None):
        if len(p['layers']) >= 100:
            raise ValueError('В проекте уже 100 слоёв')
        box = image.getbbox()
        if not box:
            raise ValueError('Изображение полностью прозрачное')
        cropped = image.crop(box)
        if position is not None:
            x, y = position[0] + box[0], position[1] + box[1]
            w, h = cropped.size
        elif image.size == (p['width'], p['height']):
            x, y, w, h = box[0], box[1], cropped.width, cropped.height
        else:
            scale = min(p['width'] / image.width, p['height'] / image.height, 1)
            x = (p['width'] - image.width * scale)/2 + box[0]*scale
            y = (p['height'] - image.height * scale)/2 + box[1]*scale
            w, h = cropped.width*scale, cropped.height*scale
        p['layers'].append(mesh_layer(name[:120] or 'Слой', self.put_image(cropped), (x, y, w, h)))
        return p

    def import_psd(self, raw, name):
        psd = PSDImage.open(io.BytesIO(raw))
        if psd.width > 4096 or psd.height > 4096 or psd.depth != 8 or psd.color_mode.name != 'RGB':
            raise ValueError('Нужен RGB PSD, 8 бит/канал, до 4096 × 4096')
        p = new_project(name, psd.width, psd.height)
        warnings = []
        for layer in psd.descendants():
            if layer.is_group():
                warnings.append('Группы PSD раскрыты в отдельные растровые слои')
                continue
            im = layer.topil()
            if im is None or not im.convert('RGBA').getbbox():
                continue
            if layer.has_mask() or layer.blend_mode.name != 'NORMAL':
                warnings.append('Маски и нестандартное смешивание: ' + layer.name + '. Подготовьте упрощённый PSD для точного совпадения.')
            self.add_image(p, im.convert('RGBA'), layer.name, (layer.left, layer.top))
            p['layers'][-1].update(visible=layer.is_visible(), opacity=layer.opacity / 255)
        self.save(p)
        return dict(project=p, warnings=list(dict.fromkeys(warnings)))

    def import_bundle(self, raw):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sum(i.file_size for i in z.infolist()) > 256*1024*1024 or len(z.infolist()) > 102:
                raise ValueError('Слишком большой архив проекта')
            p = json.loads(z.read('project.json'))
            validate(p)
            mapping = {}
            for layer in p['layers']:
                asset = layer['asset']
                if Path(asset).name != asset:
                    raise ValueError('Некорректное имя ресурса')
                if asset not in mapping:
                    mapping[asset] = self.put_image(self.image(z.read('assets/' + asset)))
                layer['asset'] = mapping[asset]
            p['id'] = uid()
            self.save(p)
            return p

    def export(self, p, kind):
        validate(p)
        stem = 'model-' + uid()[:10]
        if kind in ('motion', 'expression', 'baked-motion'):
            suffix = '.motion3.json' if kind in ('motion', 'baked-motion') else '.exp3.json'
            path = self.path('exports', stem + suffix)
            atomic_json(path, bake_physics(p) if kind == 'baked-motion' else motion(p) if kind == 'motion' else expression(p))
        elif kind == 'bundle':
            path = self.path('exports', stem + '.l2dstudio.zip')
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr('project.json', json.dumps(p, ensure_ascii=False))
                for asset in set(layer['asset'] for layer in p['layers']):
                    z.write(self.path('assets', asset), 'assets/' + asset)
        elif kind in ('png', 'psd'):
            if not p['layers']:
                raise ValueError('Сначала добавьте изображения')
            # PSD is the neutral model; PNG is the current posed preview.
            params = copy.deepcopy(p['parameters'])
            if kind == 'psd':
                for q in params:
                    q['value'] = q['default']
            psd = PSDImage.new('RGBA', (p['width'], p['height'])) if kind == 'psd' else None
            canvas = Image.new('RGBA', (p['width'], p['height']))
            images = {}
            for layer in p['layers']:
                with Image.open(self.path('assets', layer['asset'])) as im:
                    images[layer['asset']] = im.convert('RGBA')
            canvas, raster_for = render_scene(p, images, params)
            alternate_rasters = {}
            names = set()
            for layer in p['layers']:
                raster = raster_for(layer['id'])
                if psd is not None:
                    # Keep closed eyes, open mouths and other hidden alternatives
                    # editable in PSD instead of exporting fully transparent pixels.
                    neutral_opacity = layer_opacity(layer, params)
                    if neutral_opacity == 0 and layer.get('opacity_keys'):
                        alternate = copy.deepcopy(params)
                        for q in alternate:
                            keys = layer.get('opacity_keys', {}).get(q['id'], [])
                            if keys:
                                best = max(keys, key=lambda k: (k['opacity'], k['value']))
                                q['value'] = best['value']
                        signature = tuple(q['value'] for q in alternate)
                        if signature not in alternate_rasters:
                            _, alternate_rasters[signature] = render_scene(p, images, alternate)
                        raster = alternate_rasters[signature](layer['id'])
                    name, index = layer['name'], 2
                    while name in names:
                        name = layer['name'] + ' ' + str(index)
                        index += 1
                    names.add(name)
                    pl = PixelLayer.frompil(raster, psd, name=name)
                    # frompil writes the legacy Pascal name directly; the setter also
                    # stores the Unicode tag and a macroman-safe fallback (Cyrillic).
                    pl.name = name
                    pl.visible = layer['visible'] and not layer.get('mask_only', False) and neutral_opacity > 0
            path = self.path('exports', stem + '.' + kind)
            if psd is not None:
                # psd-tools 1.11 writes an RGB merged image with per-layer RGBA.
                psd._record.header.channels = 3
                psd.save(path)
                reopened = PSDImage.open(path)
                if reopened.topil() is None or len(reopened) != len(p['layers']):
                    raise RuntimeError('Не удалось проверить PSD после записи')
            else:
                canvas.save(path)
        else:
            raise ValueError('Формат не поддерживается. Выберите ZIP-проект, PNG, PSD или JSON-анимацию/выражение.')
        return dict(file=path.name, url='/exports/' + path.name)
