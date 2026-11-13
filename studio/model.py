"""Лицедей mesh model, project validation and parameter JSON exports."""
from __future__ import annotations
import copy
import math
import uuid
import numpy as np
from PIL import Image, ImageDraw

FORMAT = 'l2d-ai-studio/2'
PARAMETERS = [
    ('ParamAngleX', 'Поворот головы X', -30, 30, 0),
    ('ParamAngleY', 'Поворот головы Y', -30, 30, 0),
    ('ParamAngleZ', 'Наклон головы', -30, 30, 0),
    ('ParamEyeLOpen', 'Левый глаз', 0, 1, 1),
    ('ParamEyeROpen', 'Правый глаз', 0, 1, 1),
    ('ParamMouthOpenY', 'Открытие рта', 0, 1, 0),
    ('ParamBreath', 'Дыхание', 0, 1, 0),
]

def uid():
    return uuid.uuid4().hex

def new_project(name='Новый персонаж', width=1024, height=1536):
    return dict(format=FORMAT, id=uid(), name=name, width=width, height=height,
                layers=[], parameters=[dict(id=i, name=n, min=lo, max=hi, default=d, value=d)
                for i, n, lo, hi, d in PARAMETERS], timeline=[], duration=3, fps=30)

def mesh_layer(name, asset, bounds, size=4):
    x, y, w, h = bounds
    vertices, uv, triangles = [], [], []
    for row in range(size + 1):
        for col in range(size + 1):
            vertices.append([x + w * col / size, y + h * row / size])
            uv.append([col / size, row / size])
    for row in range(size):
        for col in range(size):
            a = row * (size + 1) + col
            triangles.extend([[a, a + 1, a + size + 1], [a + 1, a + size + 2, a + size + 1]])
    return dict(id=uid(), name=name, asset=asset, visible=True, opacity=1,
                vertices=vertices, uv=uv, triangles=triangles, keys={})

def number(value, lo, hi):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and lo <= value <= hi

def validate(p):
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(isinstance(p, dict) and p.get('format') in (FORMAT, 'l2d-ai-studio/1'), 'Неизвестный формат проекта')
    require(isinstance(p.get('name'), str) and 0 < len(p['name']) <= 120, 'Название: 1–120 символов')
    require(all(isinstance(p.get(k), int) and 16 <= p[k] <= 4096 for k in ('width', 'height')), 'Размер холста: 16–4096 px')
    require(number(p.get('duration'), .1, 120), 'Длительность: 0,1–120 с')
    require(number(p.get('fps'), 1, 120), 'Частота: 1–120 кадров/с')
    params = p.get('parameters')
    require(isinstance(params, list) and len(params) <= 100, 'Не более 100 параметров')
    ids = set()
    for param in params:
        require(isinstance(param, dict), 'Некорректный параметр')
        i = param.get('id')
        require(isinstance(i, str) and 0 < len(i) <= 80 and i not in ids, 'ID параметров должны быть уникальны')
        ids.add(i)
        require(isinstance(param.get('name'), str) and len(param['name']) <= 120, 'Некорректное имя параметра')
        require(number(param.get('min'), -10000, 10000) and number(param.get('max'), -10000, 10000)
                and param['min'] < param['max'], 'Некорректный диапазон параметра')
        require(all(number(param.get(k), param['min'], param['max']) for k in ('default', 'value')), 'Значение за пределами параметра')
    layers = p.get('layers')
    require(isinstance(layers, list) and len(layers) <= 100, 'Не более 100 слоёв')
    lids = set()
    for layer in layers:
        require(isinstance(layer, dict), 'Некорректный слой')
        i = layer.get('id')
        require(isinstance(i, str) and i not in lids, 'ID слоёв должны быть уникальны')
        lids.add(i)
        require(isinstance(layer.get('name'), str) and 0 < len(layer['name']) <= 120, 'Некорректное имя слоя')
        require(isinstance(layer.get('asset'), str) and len(layer['asset']) <= 100, 'Некорректный ресурс')
        require(isinstance(layer.get('visible'), bool) and number(layer.get('opacity'), 0, 1), 'Некорректная видимость')
        vs, uv = layer.get('vertices'), layer.get('uv')
        require(isinstance(vs, list) and 3 <= len(vs) <= 1000 and isinstance(uv, list) and len(vs) == len(uv), 'Некорректная сетка')
        for points, lo, hi in ((vs, -16384, 16384), (uv, 0, 1)):
            require(all(isinstance(v, list) and len(v) == 2 and all(number(n, lo, hi) for n in v) for v in points), 'Некорректные вершины')
        ts = layer.get('triangles')
        require(isinstance(ts, list) and 1 <= len(ts) <= 2000 and all(isinstance(t, list) and len(t) == 3
                and len(set(t)) == 3 and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v < len(vs) for v in t) for t in ts), 'Некорректные треугольники')
        keys = layer.get('keys')
        require(isinstance(keys, dict) and set(keys) <= ids, 'Ключи ссылаются на неизвестный параметр')
        for pid, entries in keys.items():
            param = next(p for p in params if p['id'] == pid)
            require(isinstance(entries, list) and len(entries) <= 30, 'Не более 30 форм на параметр')
            seen = set()
            for key in entries:
                require(isinstance(key, dict) and number(key.get('value'), param['min'], param['max']), 'Некорректное значение ключа')
                require(key['value'] not in seen, 'Повтор значения ключа')
                seen.add(key['value'])
                ds = key.get('delta')
                require(isinstance(ds, list) and len(ds) == len(vs) and all(isinstance(d, list) and len(d) == 2
                        and all(number(n, -16384, 16384) for n in d) for d in ds), 'Некорректная ключевая форма')
    frames = p.get('timeline')
    require(isinstance(frames, list) and len(frames) <= 1000, 'Не более 1000 ключевых кадров')
    seen = set()
    for frame in frames:
        require(isinstance(frame, dict) and number(frame.get('time'), 0, p['duration']), 'Кадр вне анимации')
        require(frame['time'] not in seen, 'Повтор времени ключевого кадра')
        seen.add(frame['time'])
        values = frame.get('values')
        require(isinstance(values, dict) and set(values) == ids, 'Кадр должен содержать все параметры')
        require(all(number(values[q['id']], q['min'], q['max']) for q in params), 'Некорректные значения кадра')
    from .rig import validate_rig
    validate_rig(p, number)
    return p

def deform(layer, parameters):
    result = np.array(layer['vertices'], dtype=float)
    for p in parameters:
        keys = sorted(layer['keys'].get(p['id'], []), key=lambda k: k['value'])
        if not keys:
            continue
        if not any(k['value'] == p['default'] for k in keys):
            keys.append(dict(value=p['default'], delta=np.zeros_like(result)))
            keys.sort(key=lambda k: k['value'])
        v = p['value']
        a = next((k for k in reversed(keys) if k['value'] <= v), keys[0])
        b = next((k for k in keys if k['value'] >= v), keys[-1])
        t = (v - a['value']) / (b['value'] - a['value']) if a['value'] != b['value'] else 0
        result += np.array(a['delta']) * (1-t) + np.array(b['delta']) * t
    from .rig import combination_delta
    result += np.array(combination_delta(layer, parameters))
    return result.tolist()

def layer_opacity(layer, parameters):
    result = layer['opacity']
    for q in parameters:
        keys = list(layer.get('opacity_keys', {}).get(q['id'], []))
        if not keys:
            continue
        if not any(k['value'] == q['default'] for k in keys):
            keys.append(dict(value=q['default'], opacity=1))
        keys.sort(key=lambda k: k['value'])
        a = next((k for k in reversed(keys) if k['value'] <= q['value']), keys[0])
        b = next((k for k in keys if k['value'] >= q['value']), keys[-1])
        t = (q['value']-a['value'])/(b['value']-a['value']) if b['value'] != a['value'] else 0
        result *= a['opacity']*(1-t)+b['opacity']*t
    return max(0, min(1, result))

def render_layer(layer, image, size, parameters, vertices=None):
    """Rasterize affine texture triangles, in canvas coordinates, for PSD/PNG export."""
    vertices = deform(layer, parameters) if vertices is None else vertices
    output = Image.new('RGBA', size)
    pixels = np.array(layer['uv']) * [image.width, image.height]
    for triangle in layer['triangles']:
        dest = np.array([vertices[i] for i in triangle])
        source = np.array([pixels[i] for i in triangle])
        left, top = max(0, math.floor(dest[:, 0].min())), max(0, math.floor(dest[:, 1].min()))
        right, bottom = min(size[0], math.ceil(dest[:, 0].max())), min(size[1], math.ceil(dest[:, 1].max()))
        if right <= left or bottom <= top:
            continue
        local = dest - [left, top]
        matrix = np.column_stack((local, np.ones(3)))
        if abs(np.linalg.det(matrix)) < 1e-8:
            continue
        coefficients = np.linalg.solve(matrix, source).T.flatten().tolist()
        patch = image.transform((right-left, bottom-top), Image.Transform.AFFINE, coefficients, Image.Resampling.BICUBIC)
        mask = Image.new('L', patch.size)
        ImageDraw.Draw(mask).polygon([tuple(v) for v in local], fill=255)
        output.paste(patch, (left, top), mask)
    opacity = layer_opacity(layer, parameters)
    if opacity != 1:
        output.putalpha(output.getchannel('A').point(lambda a: round(a * opacity)))
    return output

def expression(p):
    validate(p)
    return dict(Type='Live2D Expression', FadeInTime=.3, FadeOutTime=.3,
                Parameters=[dict(Id=q['id'], Value=q['value'], Blend='Overwrite') for q in p['parameters']])

def motion(p):
    validate(p)
    from .rig import export_motion
    return export_motion(p)
