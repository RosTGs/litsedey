"""Original geometric teaching example, drawn at startup without external artwork."""
from PIL import Image, ImageDraw
from .model import new_project


def seed_demo(store):
    """Create a small editable robot with blink, mouth, breathing and head movement."""
    p = new_project('Бот · первые движения', 640, 800)
    p['parameters'] = [q for q in p['parameters'] if q['id'] != 'ParamAngleY']
    head_parts = []

    def part(name, draw, head=False):
        image = Image.new('RGBA', (640, 800))
        draw(ImageDraw.Draw(image))
        store.add_image(p, image, name)
        layer = p['layers'][-1]
        if head:
            head_parts.append(layer)
        return layer

    part('Опора', lambda d: d.rounded_rectangle((210, 660, 430, 714), radius=24, fill='#404965'))
    body = part('Корпус', lambda d: d.rounded_rectangle((190, 395, 450, 682), radius=55, fill='#8068db'))
    part('Шея', lambda d: d.rounded_rectangle((276, 350, 364, 425), radius=24, fill='#b3a4f0'))
    part('Антенна', lambda d: (d.line((320, 175, 320, 113), fill='#b3a4f0', width=14),
                              d.ellipse((296, 76, 344, 124), fill='#f3bc72')), head=True)
    part('Голова', lambda d: d.rounded_rectangle((160, 166, 480, 375), radius=70, fill='#d5edf0'), head=True)
    for pid, x, name in [('ParamEyeLOpen', 378, 'Левый глаз'), ('ParamEyeROpen', 262, 'Правый глаз')]:
        eye = part(name, lambda d, x=x: d.ellipse((x-19, 235, x+19, 283), fill='#303c55'), head=True)
        eye['keys'][pid] = [dict(value=0, delta=[[0, (259-y)*.90] for x, y in eye['vertices']])]
    mouth = part('Рот', lambda d: d.rounded_rectangle((295, 311, 345, 327), radius=8, fill='#53506e'), head=True)
    mouth['keys']['ParamMouthOpenY'] = [dict(value=1, delta=[[0, (y-319)*1.8] for x, y in mouth['vertices']])]
    for layer in head_parts:
        layer['keys']['ParamAngleX'] = [dict(value=v, delta=[[v*.7, 0] for _ in layer['vertices']]) for v in (-30, 30)]
        # A modest hand-authored tilt; this example does not pretend to create perspective.
        layer['keys']['ParamAngleZ'] = [dict(value=v, delta=[[-(y-350)*v/150, (x-320)*v/150]
                                                           for x, y in layer['vertices']]) for v in (-30, 30)]
    body['keys']['ParamBreath'] = [dict(value=1, delta=[[0, -8*(682-y)/287] for x, y in body['vertices']])]
    p['duration'] = 4
    p['tracks'] = {
        'ParamAngleX': [dict(time=t, value=v, interpolation='smooth') for t, v in [(0, 0), (1, -20), (2, 0), (3, 20), (4, 0)]],
        'ParamBreath': [dict(time=t, value=v, interpolation='smooth') for t, v in [(0, 0), (2, 1), (4, 0)]],
    }
    for pid in ('ParamEyeLOpen', 'ParamEyeROpen'):
        p['tracks'][pid] = [dict(time=t, value=v, interpolation='linear') for t, v in [(0, 1), (1.5, 1), (1.65, 0), (1.85, 1), (4, 1)]]
    p['notes'] = ('Новый учебный пример Лицедей, нарисованный кодом из простых фигур. Нажмите ▶ или двигайте параметры. '
                  'Глаза моргают независимо, рот открывается. Горизонтальное движение демонстрирует ключевые формы, '
                  'а не готовый пространственный поворот головы. Исходник: studio/demo.py, лицензия MIT.')
    return store.save(p)
