"""Deterministic assembly recipes for Лицедей; creates a copy and never edits source artwork."""
import copy
import math
from .model import uid, validate

ROLES = [('white','Белок',True),('iris','Радужка',True),('upper','Верхнее веко',True),('lower','Нижнее веко',False),('closed','Закрытый глаз',True)]
PARAMS = [('ParamEyeLOpen','Левый глаз персонажа',0,1,1),('ParamEyeROpen','Правый глаз персонажа',0,1,1),('ParamEyeBallX','Взгляд влево / вправо',-1,1,0),('ParamEyeBallY','Взгляд вниз / вверх',-1,1,0)]

def bounds(layer):
    vs=layer['vertices'];xs=[v[0] for v in vs];ys=[v[1] for v in vs]
    return [min(xs),min(ys),max(xs)-min(xs),max(ys)-min(ys)]

def analyze(project):
    validate(project)
    # Suggest only exact, unambiguous labels; unrecognized anatomy stays unassigned.
    suggestions={};ambiguous=[]
    for side,word in [('L','левый'),('R','правый')]:
        for role,label,required in ROLES:
            aliases={'white':'EyeWhite','iris':'Iris','upper':'UpperLid','lower':'LowerLid','closed':'ClosedEye'}
            names={f'{label} · {word}'.casefold(),f'{aliases[role]}_{side}'.casefold()}
            found=[l['id'] for l in project['layers'] if l['name'].casefold() in names]
            key=side+'.'+role
            if len(found)==1:suggestions[key]=found[0]
            elif len(found)>1:ambiguous.append(key)
    return dict(template='eyes-v1',roles=[dict(key=s+'.'+r,label=n+' · '+('левый' if s=='L' else 'правый'),required=req) for s in ['L','R'] for r,n,req in ROLES],layers=[dict(id=l['id'],name=l['name'],bounds=bounds(l),parent=l.get('parent')) for l in project['layers']],suggestions=suggestions,ambiguous=ambiguous)

def plan(project,recipe):
    validate(project)
    errors=[];warnings=[]
    if not isinstance(recipe,dict) or recipe.get('template')!='eyes-v1':raise ValueError('Поддерживается шаблон eyes-v1')
    mapping=recipe.get('mapping',{})
    if not isinstance(mapping,dict):raise ValueError('Назначения слоёв должны быть объектом')
    allowed={s+'.'+r for s in ['L','R'] for r,_,_ in ROLES}
    if set(mapping)-allowed:errors.append('В схеме есть неизвестные роли')
    layers={l['id']:l for l in project['layers']};used=set()
    for side in ['L','R']:
        parents=set()
        for role,label,required in ROLES:
            lid=mapping.get(side+'.'+role)
            if not lid:
                if required:errors.append(label+': назначьте '+('левый' if side=='L' else 'правый')+' глаз')
                continue
            if not isinstance(lid,str) or lid not in layers:
                errors.append('Слой для '+side+'.'+role+' не найден');continue
            if lid in used:errors.append('Один слой назначен нескольким деталям глаз')
            used.add(lid);l=layers[lid];parents.add(l.get('parent'))
            if min(bounds(l)[2:])<1:errors.append('Сетка слоя '+l['name']+' слишком узкая')
            if l.get('combinations'):errors.append('У слоя '+l['name']+' есть сочетания параметров. Для этого шаблона нужна базовая графика без сочетаний.')
        if len(parents)>1:errors.append('Детали '+side+' глаза должны иметь одного родителя')
    for pid,name,lo,hi,default in PARAMS:
        q=next((q for q in project['parameters'] if q['id']==pid),None)
        if q and (q['min']!=lo or q['max']!=hi or q['default']!=default):errors.append('Несовместимый диапазон '+pid+'; нужен '+str(lo)+'…'+str(hi)+', нейтраль '+str(default))
    options=recipe.get('options',{})
    if not isinstance(options,dict):raise ValueError('Некорректные настройки шаблона')
    for key,default,lo,hi in [('threshold',.1,.02,.3),('gaze_x',.16,.01,.4),('gaze_y',.22,.01,.4)]:
        v=options.get(key,default)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:errors.append('Некорректная настройка '+key)
    if len(project['parameters'])+sum(not any(q['id']==pid for q in project['parameters']) for pid,*_ in PARAMS)>100:errors.append('Недостаточно места для параметров глаз')
    if any(layers[i].get('keys') or layers[i].get('opacity_keys') for i in used):warnings.append('В новой копии будут заменены ключи моргания и взгляда назначенных деталей. Другие параметры сохраняются.')
    warnings.extend(['L/R обозначают стороны персонажа: его левый глаз находится справа для зрителя.','Автоматическая сетка даёт стартовую форму. После сборки проверьте промежуточное закрытие и поправьте веки под рисунок.'])
    return dict(ok=not errors,errors=errors,warnings=warnings,operations=['Новая копия проекта','4 параметра глаз','Маска каждой радужки по своему белку','Независимые формы моргания','Переключение на нарисованное закрытое веко','Демонстрационная анимация 5 секунд'],assigned=len(used))

def build(project,recipe):
    report=plan(project,recipe)
    if not report['ok']:raise ValueError('; '.join(report['errors']))
    p=copy.deepcopy(project);p['id']=uid();p['name']=(str(recipe.get('name') or project['name']+' · быстрая сборка'))[:120]
    mapping=recipe['mapping'];layers={l['id']:l for l in p['layers']};options=recipe.get('options',{});threshold=options.get('threshold',.1)
    for pid,name,lo,hi,default in PARAMS:
        if not any(q['id']==pid for q in p['parameters']):p['parameters'].append(dict(id=pid,name=name,min=lo,max=hi,default=default,value=default))
    for side in ['L','R']:
        pid='ParamEye'+side+'Open';parts={r:layers[mapping[side+'.'+r]] for r,_,_ in ROLES if mapping.get(side+'.'+r)}
        white=parts['white'];x,y,w,h=bounds(white);cy=y+h/2
        for r,l in parts.items():
            l.update(visible=True,opacity=1,mask_only=False)
            l.setdefault('opacity_keys',{})[pid]=[dict(value=0,opacity=1 if r=='closed' else 0),dict(value=threshold,opacity=0 if r=='closed' else 1),dict(value=1,opacity=0 if r=='closed' else 1)]
            l['keys'].pop(pid,None)
            l['keys'].pop('ParamEyeBallX',None);l['keys'].pop('ParamEyeBallY',None)
            if r in ('white','upper','lower'):
                delta=[[0,(cy-vy)*.965 if r=='white' else h*.38 if r=='upper' else -h*.38] for vx,vy in l['vertices']]
                l['keys'][pid]=[dict(value=0,delta=delta)]
        parts['iris']['masks']=[white['id']];parts['iris']['mask_invert']=False
        for axis,scale in [('X',w*options.get('gaze_x',.16)),('Y',h*options.get('gaze_y',.22))]:
            parts['iris']['keys']['ParamEyeBall'+axis]=[dict(value=v,delta=[[v*scale,0] if axis=='X' else [0,-v*scale] for _ in parts['iris']['vertices']]) for v in [-1,1]]
    p.update(duration=5,loop=True,timeline=[],tracks={})
    for q in p['parameters']:q['value']=q['default']
    for pid,points in [('ParamEyeLOpen',[(0,1),(.7,1),(.84,0),(.98,1),(2,1),(2.2,0),(2.5,1),(4,1),(4.14,0),(4.28,1),(5,1)]),('ParamEyeROpen',[(0,1),(.7,1),(.84,0),(.98,1),(4,1),(4.14,0),(4.28,1),(5,1)]),('ParamEyeBallX',[(0,0),(1,0),(1.5,-1),(2,-1),(3,1),(4,0),(5,0)])]:
        p['tracks'][pid]=[dict(time=t,value=v,interpolation='linear') for t,v in points]
    p['assembly']=dict(template='eyes-v1',source_project=project['id'],recipe=copy.deepcopy(recipe))
    validate(p)
    return p,report
