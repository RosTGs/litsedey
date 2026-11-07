"""Kadr hierarchy, masks and independent animation curves."""
import math
import copy
from PIL import Image, ImageChops


def validate_rig(p, number):
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    ds = p.get('deformers', [])
    require(isinstance(ds, list) and len(ds) <= 100, 'Не более 100 деформеров')
    nodes = p['layers'] + ds
    ids = [n.get('id') for n in nodes]
    require(all(isinstance(i, str) and 0 < len(i) <= 100 for i in ids) and len(set(ids)) == len(ids), 'ID объектов должны быть уникальны')
    dids = {d['id'] for d in ds}
    params = {q['id']: q for q in p['parameters']}
    def vectors(vs, count=None):
        return isinstance(vs, list) and (count is None or len(vs) == count) and all(isinstance(v, list) and len(v) == 2 and all(number(x, -16384, 16384) for x in v) for v in vs)
    for d in ds:
        require(d.get('type') in ('warp', 'rotation'), 'Неизвестный тип деформера')
        require(isinstance(d.get('name'), str) and 0 < len(d['name']) <= 120, 'Некорректное имя деформера')
        if d['type'] == 'warp':
            n = d.get('divisions')
            require(type(n) is int and 1 <= n <= 8, 'Сетка деформера: 1–8 делений')
            b = d.get('bounds')
            require(isinstance(b, list) and len(b) == 4 and all(number(x, -16384, 16384) for x in b) and b[2] > 0 and b[3] > 0, 'Некорректные границы деформера')
            count = (n + 1) ** 2
        else:
            count = 2
        require(vectors(d.get('vertices'), count), 'Некорректные точки деформера')
        if d['type'] == 'rotation':
            require(vectors(d.get('rest', d['vertices']), 2) and math.dist(*d.get('rest', d['vertices'])) >= 1, 'Ось вращения слишком короткая')
        keys = d.get('keys')
        require(isinstance(keys, dict) and set(keys) <= set(params), 'Некорректные ключи деформера')
        for pid, entries in keys.items():
            q = params[pid]
            require(isinstance(entries, list) and len(entries) <= 30, 'Не более 30 форм на параметр')
            seen = set()
            for k in entries:
                require(isinstance(k, dict) and number(k.get('value'), q['min'], q['max']) and k['value'] not in seen and vectors(k.get('delta'), count), 'Некорректная форма деформера')
                seen.add(k['value'])
    for node in nodes:
        bind = node.get('bind', [1,0,0,1,0,0])
        require(isinstance(bind, list) and len(bind) == 6 and all(number(v,-1e8,1e8) for v in bind)
                and abs(bind[0]*bind[3]-bind[1]*bind[2]) > 1e-10, 'Некорректная привязка объекта')
        require(node.get('rotation_mode', 'legacy') in ('legacy','polar'), 'Неизвестный режим вращения')
        combos = node.get('combinations', [])
        require(isinstance(combos, list) and len(combos) <= 10, 'Не более 10 сочетаний параметров на объект')
        pairs = set()
        for c in combos:
            require(isinstance(c, dict) and isinstance(c.get('parameters'), list) and len(c['parameters']) == 2 and all(isinstance(i, str) and i in params for i in c['parameters']) and c['parameters'][0] != c['parameters'][1], 'Некорректные оси сочетания')
            pair = tuple(sorted(c['parameters']))
            require(pair not in pairs, 'Повтор сочетания параметров')
            pairs.add(pair)
            require(isinstance(c.get('keys'), list) and len(c['keys']) <= 100, 'Не более 100 форм на сочетание')
            seen = set()
            for k in c['keys']:
                require(isinstance(k, dict) and isinstance(k.get('values'), list) and len(k['values']) == 2 and all(number(v, params[i]['min'], params[i]['max']) for v, i in zip(k['values'], c['parameters'])), 'Некорректные значения сочетания')
                point=tuple(k['values'])
                require(point not in seen and vectors(k.get('delta'), len(node['vertices'])), 'Повтор или повреждённая форма сочетания')
                seen.add(point)
    by_id = {n['id']: n for n in nodes}
    for n in nodes:
        parent = n.get('parent')
        require(parent is None or parent in dids, 'Родитель должен быть деформером')
        seen = {n['id']}
        while parent is not None:
            require(parent not in seen, 'Цикл в иерархии деформеров')
            seen.add(parent)
            parent = by_id[parent].get('parent')
    lids = {l['id'] for l in p['layers']}
    for l in p['layers']:
        opacity_keys = l.get('opacity_keys', {})
        require(isinstance(opacity_keys, dict) and set(opacity_keys) <= set(params), 'Неизвестный параметр прозрачности')
        for pid, keys in opacity_keys.items():
            q = params[pid]
            require(isinstance(keys, list) and len(keys) <= 30, 'Не более 30 ключей прозрачности')
            seen = set()
            for k in keys:
                require(isinstance(k, dict) and number(k.get('value'), q['min'], q['max']) and k['value'] not in seen and number(k.get('opacity'), 0, 1), 'Некорректный ключ прозрачности')
                seen.add(k['value'])
        masks = l.get('masks', [])
        require(isinstance(masks, list) and len(masks) <= 8 and all(isinstance(x, str) and x in lids for x in masks) and len(set(masks)) == len(masks), 'Некорректные маски слоя')
        require(type(l.get('mask_only', False)) is bool and type(l.get('mask_invert', False)) is bool, 'Некорректный режим маски')
    done = set()
    def visit(i, active):
        require(i not in active, 'Цикл в масках слоёв')
        if i in done:
            return
        for m in by_id[i].get('masks', []):
            visit(m, active | {i})
        done.add(i)
    for i in lids:
        visit(i, set())
    tracks = p.get('tracks')
    if tracks is not None:
        require(isinstance(tracks, dict) and set(tracks) <= set(params), 'Неизвестная дорожка анимации')
        require(sum(len(v) if isinstance(v, list) else 100001 for v in tracks.values()) <= 20000, 'Слишком много ключей анимации')
        for pid, keys in tracks.items():
            require(isinstance(keys, list) and len(keys) <= 1000, 'Не более 1000 ключей на дорожку')
            seen = set()
            for k in keys:
                require(isinstance(k, dict) and number(k.get('time'), 0, p['duration']) and k['time'] not in seen, 'Повтор или неверное время ключа')
                seen.add(k['time'])
                require(number(k.get('value'), params[pid]['min'], params[pid]['max']) and k.get('interpolation', 'linear') in ('linear', 'smooth', 'step'), 'Некорректная кривая анимации')
    physics = p.get('physics', [])
    require(isinstance(physics, list) and len(physics) <= 16, 'Не более 16 групп физики')
    seen, outputs = set(), set()
    for g in physics:
        require(isinstance(g, dict) and isinstance(g.get('id'), str) and g['id'] not in seen, 'Некорректный ID физики')
        seen.add(g['id'])
        require(isinstance(g.get('name'), str) and 0 < len(g['name']) <= 120, 'Некорректное имя физики')
        require(g.get('input') in params and g.get('output') in params and g['input'] != g['output'] and g['output'] not in outputs, 'Физика: выберите разные вход и уникальный выход')
        outputs.add(g['output'])
        require(number(g.get('frequency'), .1, 10) and number(g.get('damping'), .05, 2) and number(g.get('strength'), -2, 2) and type(g.get('enabled', True)) is bool, 'Некорректные настройки физики')
    require(not any(g['input'] in outputs for g in physics), 'Цепочки физики пока не поддерживаются: вход не должен быть выходом другой группы')
    require(type(p.get('loop', True)) is bool, 'Некорректный режим повтора')


def local_vertices(node, parameters):
    # Reuse the additive keyform interpolator without recursing through parents.
    from .model import deform
    if node.get('type') != 'rotation' or node.get('rotation_mode') != 'polar':
        return deform(node, parameters)
    (cx, cy), (hx, hy) = node['vertices']
    length = math.hypot(hx-cx, hy-cy)
    if length < 1e-8:
        return deform(node, parameters)
    angle = math.atan2(hy-cy, hx-cx)
    out_angle, out_length = angle, length
    ox, oy = cx, cy
    for q in parameters:
        keys = copy.deepcopy(node['keys'].get(q['id'], []))
        if not keys:
            continue
        if not any(k['value'] == q['default'] for k in keys):
            keys.append(dict(value=q['default'],delta=[[0,0],[0,0]]))
        keys.sort(key=lambda k:k['value'])
        forms = []
        for k in keys:
            (dx,dy),(ex,ey) = k['delta']
            vx,vy = hx+ex-cx-dx, hy+ey-cy-dy
            a = math.atan2(vy,vx)-angle
            while a > math.pi: a -= 2*math.pi
            while a < -math.pi: a += 2*math.pi
            if forms:
                while a-forms[-1][3] > math.pi: a -= 2*math.pi
                while a-forms[-1][3] < -math.pi: a += 2*math.pi
            forms.append((k['value'],dx,dy,a,math.hypot(vx,vy)/length))
        a = next((k for k in reversed(forms) if k[0] <= q['value']), forms[0])
        b = next((k for k in forms if k[0] >= q['value']), forms[-1])
        t = (q['value']-a[0])/(b[0]-a[0]) if a[0] != b[0] else 0
        v = [a[i]*(1-t)+b[i]*t for i in range(1,5)]
        ox += v[0]; oy += v[1]; out_angle += v[2]; out_length *= v[3]
    points = [[ox,oy],[ox+out_length*math.cos(out_angle),oy+out_length*math.sin(out_angle)]]
    return [[x+dx,y+dy] for (x,y),(dx,dy) in zip(points,combination_delta(node,parameters))]


def bind_point(node, point):
    a,b,c,d,e,f = node.get('bind',[1,0,0,1,0,0])
    x,y = point
    return [a*x+c*y+e,b*x+d*y+f]


def transform_point(d, point, parameters, current=None):
    current = local_vertices(d, parameters) if current is None else current
    x, y = point
    if d['type'] == 'rotation':
        (px, py), (hx, hy) = d.get('rest', d['vertices'])
        (cx, cy), (tx, ty) = current
        bx, by = hx-px, hy-py
        den = bx*bx+by*by
        a, b = ((tx-cx)*bx+(ty-cy)*by)/den, ((ty-cy)*bx-(tx-cx)*by)/den
        return bind_point(d, [cx+a*(x-px)-b*(y-py), cy+b*(x-px)+a*(y-py)])
    bx, by, w, h = d['bounds']
    n = d['divisions']
    u, v = (x-bx)/w*n, (y-by)/h*n
    col, row = max(0, min(n-1, math.floor(u))), max(0, min(n-1, math.floor(v)))
    u, v = u-col, v-row  # extend the edge cell linearly beyond the envelope
    indices = [row*(n+1)+col, row*(n+1)+col+1, (row+1)*(n+1)+col, (row+1)*(n+1)+col+1]
    weights = [(1-u)*(1-v), u*(1-v), (1-u)*v, u*v]
    return bind_point(d, [sum(current[i][a]*t for i, t in zip(indices, weights)) for a in (0, 1)])


def world_vertices(node, project, parameters=None):
    parameters = parameters if parameters is not None else project['parameters']
    result = [bind_point(node,v) for v in local_vertices(node, parameters)]
    lookup = {d['id']: d for d in project.get('deformers', [])}
    parent = node.get('parent')
    while parent:
        d = lookup[parent]
        current = local_vertices(d, parameters)
        result = [transform_point(d, v, parameters, current) for v in result]
        parent = d.get('parent')
    return result


def render_scene(project, images, parameters=None):
    from .model import render_layer
    parameters = parameters if parameters is not None else project['parameters']
    lookup = {l['id']: l for l in project['layers']}
    cache = {}
    size = (project['width'], project['height'])
    def raster(i):
        if i in cache:
            return cache[i]
        l = lookup[i]
        result = render_layer(l, images[l['asset']], size, parameters, world_vertices(l, project, parameters))
        if l.get('masks'):
            mask = Image.new('RGBA', size)
            for mid in l['masks']:
                mask.alpha_composite(raster(mid))
            alpha = mask.getchannel('A')
            if l.get('mask_invert'):
                alpha = ImageChops.invert(alpha)
            result.putalpha(ImageChops.multiply(result.getchannel('A'), alpha))
        cache[i] = result
        return result
    canvas = Image.new('RGBA', size)
    for l in project['layers']:
        if l['visible'] and not l.get('mask_only', False):
            canvas.alpha_composite(raster(l['id']))
    return canvas, raster


def tracks(project):
    if 'tracks' in project:
        return project['tracks']
    return {q['id']: [dict(time=f['time'], value=f['values'][q['id']], interpolation='linear') for f in project['timeline']] for q in project['parameters']}


def sample_track(keys, time, default):
    if not keys:
        return default
    keys = sorted(keys, key=lambda k: k['time'])
    a = next((k for k in reversed(keys) if k['time'] <= time), keys[0])
    b = next((k for k in keys if k['time'] >= time), keys[-1])
    t = (time-a['time'])/(b['time']-a['time']) if a['time'] != b['time'] else 0
    mode = a.get('interpolation', 'linear')
    if mode == 'step':
        t = 0
    elif mode == 'smooth':
        t = t*t*(3-2*t)
    return a['value']*(1-t)+b['value']*t


def export_motion(project):
    curves, segments_count, points_count = [], 0, 0
    source = tracks(project)
    if not any(source.values()):
        raise ValueError('Добавьте ключи на дорожки анимации')
    for q in project['parameters']:
        keys = sorted(copy.deepcopy(source.get(q['id'], [])), key=lambda k: k['time'])
        if not keys:
            continue  # Untouched parameters must not be overwritten by this motion.
        if keys[0]['time'] > 0:
            keys.insert(0, dict(time=0, value=keys[0]['value'], interpolation='linear'))
        if keys[-1]['time'] < project['duration']:
            keys.append(dict(time=project['duration'], value=keys[-1]['value']))
        data = [keys[0]['time'], keys[0]['value']]
        points_count += 1
        for a, b in zip(keys, keys[1:]):
            mode = a.get('interpolation', 'linear')
            if mode == 'smooth':
                dt = (b['time']-a['time'])/3
                data += [1, a['time']+dt, a['value'], b['time']-dt, b['value'], b['time'], b['value']]
                points_count += 3
            else:
                data += [2 if mode == 'step' else 0, b['time'], b['value']]
                points_count += 1
            segments_count += 1
        curves.append(dict(Target='Parameter', Id=q['id'], Segments=data))
    return dict(Version=3, Meta=dict(Duration=project['duration'], Fps=project['fps'], Loop=project.get('loop', True), AreBeziersRestricted=True, CurveCount=len(curves), TotalSegmentCount=segments_count, TotalPointCount=points_count, UserDataCount=0, TotalUserDataSize=0), Curves=curves, UserData=[])


def physics_frames(project, times):
    """Fixed 120 Hz springs, interpolated at output times exactly as in the UI."""
    groups=[g for g in project.get('physics', []) if g.get('enabled', True)]
    source=tracks(project)
    params={q['id']:q for q in project['parameters']}
    states=[[0.0,0.0] for _ in groups]
    frames=[]
    for step in range(math.ceil(project['duration']*120)+1):
        for index,g in enumerate(groups):
            q=params[g['input']]
            value=sample_track(source.get(q['id'], []),step/120,q['default'])-q['default']
            den=q['max']-q['default'] if value>=0 else q['default']-q['min']
            force=value/max(den,1e-8)*g['strength']
            x,v=states[index];omega=2*math.pi*g['frequency']
            if step:
                v+=(omega*omega*(force-x)-2*g['damping']*omega*v)/120
                x+=v/120
            states[index]=[x,v]
        frames.append([s[0] for s in states])
    for target in times:
        values={i:sample_track(source.get(i, []),target,q['default']) for i,q in params.items()}
        a=min(len(frames)-1,math.floor(target*120));b=min(a+1,len(frames)-1);f=target*120-a
        for index,g in enumerate(groups):
            q=params[g['output']];x=frames[a][index]*(1-f)+frames[b][index]*f
            span=q['max']-q['default'] if x>=0 else q['default']-q['min']
            values[q['id']]=min(q['max'],max(q['min'],values[q['id']]+x*span))
        yield values


def bake_physics(project):
    if not project.get('physics'):
        raise ValueError('Сначала настройте физику')
    result=copy.deepcopy(project)
    count=math.ceil(project['duration']*project['fps'])
    times=[min(i/project['fps'],project['duration']) for i in range(count+1)]
    animated=set(tracks(project))|{g['output'] for g in project['physics'] if g.get('enabled', True)}
    result['tracks']={i:[] for i in animated}
    for t,values in zip(times,physics_frames(project,times)):
        for i in animated:
            result['tracks'][i].append(dict(time=t,value=values[i],interpolation='linear'))
    # Sampling export may exceed the editor's 1000 editable-key limit; it does
    # not change the saved project and export_motion only serializes its curves.
    return export_motion(result)


def combination_delta(node, parameters):
    params={q['id']:q for q in parameters}
    result=[[0.0,0.0] for _ in node['vertices']]
    for combo in node.get('combinations', []):
        ranges=[]
        for axis,pid in enumerate(combo['parameters']):
            q=params[pid]
            anchors=sorted({q['min'],q['default'],q['max']}|{k['values'][axis] for k in combo['keys']})
            a=next((v for v in reversed(anchors) if v<=q['value']),anchors[0])
            b=next((v for v in anchors if v>=q['value']),anchors[-1])
            t=(q['value']-a)/(b-a) if b!=a else 0
            ranges.append([(a,1-t),(b,t)])
        for x,wx in ranges[0]:
            for y,wy in ranges[1]:
                key=next((k for k in combo['keys'] if k['values']==[x,y]),None)
                if key:
                    for v,delta in zip(result,key['delta']):
                        v[0]+=delta[0]*wx*wy;v[1]+=delta[1]*wx*wy
    return result
