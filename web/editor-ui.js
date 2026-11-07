'use strict';
function matchesPartSearch(name,query){const words=name.toLocaleLowerCase().split(/[^\p{L}\p{N}]+/u);return query.trim().toLocaleLowerCase().split(/\s+/).every(q=>!q||words.some(w=>w.startsWith(q)));}
function firstPaintLayer(){return [...S.project.layers].reverse().find(l=>!l.mask_only&&l.visible)?.id||S.project.layers.find(l=>!l.mask_only)?.id;}
function showSaveConflict(){
  if($('#conflict-copy'))return;
  modal('Обнаружена другая версия',`<p>В другом окне или помощником сохранены новые изменения. Ваша работа остаётся в этом окне. Сохраните её отдельным проектом, чтобы сохранить обе версии.</p><div class="dialog-actions"><button id="conflict-copy" class="primary">Сохранить мою версию копией</button></div>`);
  $('#conflict-copy').onclick=safely(async()=>{const p=await api('save-copy',{project:clone(S.project)});S.conflict=false;S.dirty=false;await adopt(p);closeModal();toast('Обе версии сохранены. Открыта ваша копия.');});
}
function editorInspectorHTML(l){
  if(S.tab!=='model')return '';
  return `<section class="inspector-section editor-workbench"><div class="inline"><h3>Мастерская форм</h3><span class="chip">0.4</span></div><p class="hint">Проверяйте поворот вместе с мимикой. Деталь и её ключи остаются редактируемыми.</p><div class="two-fields">${['X','Y'].map((axis,i)=>`<div class="field"><label for="pose-${axis}">Ось ${axis}</label><select id="pose-${axis}">${S.project.parameters.map(q=>`<option value="${esc(q.id)}" ${q.id===poseAxes()[i]?'selected':''}>${esc(q.name)}</option>`).join('')}</select></div>`).join('')}</div><div class="pose-grid" id="pose-grid" aria-label="Девять поз выбранных параметров"></div><div class="mini-actions"><button id="edit-pose">Править эту позу</button><button id="sweep-pose">Проверить движение</button></div><button id="add-head-axes" class="quiet wide">Добавить недостающие X/Y головы</button><div class="mini-actions"><button id="onion-pose">${S.onion?'Убрать':'Запомнить'} контур</button><button id="check-mesh">Проверить сетки</button></div><p class="hint">● — поправка сочетания, ◇ — без поправки. «Править» создаёт ключ для выбранной детали. Это не автоматическая генерация поворота.</p>${l?`<details class="mesh-workshop" open><summary>Инструменты детали</summary><label class="check"><input id="lock-part" type="checkbox" ${l.locked?'checked':''}> Зафиксировать на холсте</label>${l.type==='rotation'?`<label class="check"><input id="polar-rotation" type="checkbox" ${l.rotation_mode==='polar'?'checked':''}> Сохранять размер при вращении</label><p class="hint">Для старых ригов включается вручную. Опорные формы сохраняются, движение между ними изменится.</p>`:''}${!l.type?`<div class="mini-actions"><button id="insert-point">Добавить точку</button><button id="subdivide-mesh">Уплотнить сетку</button></div><button id="delete-point" class="wide">Удалить выбранную внутреннюю точку</button><div class="field"><label for="soft-radius">Мягкое влияние, px</label><input id="soft-radius" type="number" min="0" max="1000" value="${S.softRadius||0}"></div><p class="hint">Shift + щелчок — несколько точек. Новые точки наследуют формы и сочетания. Удаление доступно для внутренней точки с тремя соседями.</p><button id="replace-art" class="wide">Заменить рисунок, сохранить риг</button>`:''}${l.type==='warp'?'<button id="refine-warp" class="wide">Уплотнить решётку ×2</button>':''}</details>`:''}</section>`;
}
function poseAxes(){const ids=S.project.parameters.map(q=>q.id);return [ids.includes(S.poseX)?S.poseX:ids.includes('ParamAngleX')?'ParamAngleX':ids[0],ids.includes(S.poseY)?S.poseY:ids.includes('ParamAngleY')?'ParamAngleY':ids[1]];}
function poseGrid(){
  const el=$('#pose-grid');if(!el)return;
  const [x,y]=poseAxes().map(id=>S.project.parameters.find(q=>q.id===id));
  if(!x||!y||x===y){el.innerHTML='<p class="hint">Выберите два разных параметра.</p>';return;}
  const l=layer(),c=l?.combinations?.find(c=>c.parameters.includes(x.id)&&c.parameters.includes(y.id));
  el.innerHTML=[y.max,y.default,y.min].flatMap((vy,row)=>[x.min,x.default,x.max].map((vx,col)=>{
    const keyed=c?.keys.some(k=>k.values[c.parameters.indexOf(x.id)]===vx&&k.values[c.parameters.indexOf(y.id)]===vy),active=Math.abs(x.value-vx)<1e-6&&Math.abs(y.value-vy)<1e-6;
    return `<button data-pose-x="${vx}" data-pose-y="${vy}" class="${active?'active':''}" aria-pressed="${active}" aria-label="${esc(x.name)} ${vx}, ${esc(y.name)} ${vy}"><span>${[['↖','↑','↗'],['←','•','→'],['↙','↓','↘']][row][col]}</span><small>${keyed?'●':'◇'} ${vx} / ${vy}</small></button>`;
  })).join('');
  $$('[data-pose-x]').forEach(b=>b.onclick=()=>{stop();S.keyMode=false;S.comboMode=false;change(()=>{x.value=+b.dataset.poseX;y.value=+b.dataset.poseY;},false);syncParams();poseGrid();});
}
function editCurrentPose(){
  const l=layer(),ids=poseAxes();if(!l)throw Error('Выберите деталь или деформер');if(l.locked)throw Error('Снимите фиксацию детали');
  if(!ids[0]||!ids[1]||ids[0]===ids[1])throw Error('Выберите две разные оси');
  let c=l.combinations?.find(c=>c.parameters.every(id=>ids.includes(id)));
  if(!c&&(l.combinations||[]).length>=10)throw Error('Не более 10 сочетаний на объект');
  // Other parameters stay as preview context; the correction is stored for these axes.
  change(()=>{l.combinations??=[];if(!c){c={parameters:ids,keys:[]};l.combinations.push(c);}S.param=c.parameters[0];S.comboSecond=c.parameters[1];S.comboMode=true;S.keyMode=true;ensureCombinationKey();S.tool='mesh';});
}
function stopPoseSweep(){if($('#sweep-pose'))$('#sweep-pose').textContent='Проверить движение';S.sweepToken=(S.sweepToken||0)+1;S.sweeping=false;}
function sweepPose(){
  if(S.sweeping){stopPoseSweep();renderInspector();return;}
  if(Capture.active||Capture.starting)throw Error('Остановите камеру перед проверкой');
  const qs=poseAxes().map(id=>S.project.parameters.find(q=>q.id===id));if(!qs[0]||!qs[1]||qs[0]===qs[1])throw Error('Выберите две разные оси');
  stop();S.keyMode=false;S.comboMode=false;const token=++S.sweepToken,start=performance.now();S.sweeping=true;$('#sweep-pose').textContent='Остановить проверку';
  const path=[[0,0],[-1,0],[-1,1],[0,1],[1,1],[1,0],[1,-1],[0,-1],[-1,-1],[-1,0],[0,0]];
  const tick=now=>{if(token!==S.sweepToken||!S.sweeping)return;const t=Math.min((now-start)/650,path.length-1),i=Math.min(path.length-2,Math.floor(t)),f=t-i,u=f*f*(3-2*f);
    qs.forEach((q,j)=>{const v=path[i][j]*(1-u)+path[i+1][j]*u;q.value=q.default+v*(v>=0?q.max-q.default:q.default-q.min);});syncParams();poseGrid();draw();
    if(t<path.length-1)requestAnimationFrame(tick);else{stopPoseSweep();dirty();renderInspector();}};requestAnimationFrame(tick);
}
function bindEditorInspector(l){
  if(S.tab!=='model')return;
  for(const axis of ['X','Y'])$('#pose-'+axis).onchange=e=>{stopPoseSweep();S['pose'+axis]=e.target.value;poseGrid();};
  poseGrid();$('#edit-pose').onclick=safely(editCurrentPose);$('#sweep-pose').onclick=safely(sweepPose);
  $('#add-head-axes').onclick=safely(()=>change(()=>{for(const [id,name] of [['ParamAngleX','Поворот головы X'],['ParamAngleY','Поворот головы Y']])if(!S.project.parameters.some(q=>q.id===id)){if(S.project.parameters.length>=100)throw Error('Достигнут предел параметров');S.project.parameters.push({id,name,min:-30,max:30,default:0,value:0});S.project.tracks[id]=[];}S.poseX='ParamAngleX';S.poseY='ParamAngleY';}));
  $('#onion-pose').onclick=()=>{S.onion=S.onion?null:{project:S.project.id,layers:S.project.layers.filter(l=>l.visible&&!l.mask_only).map(l=>({vertices:vertices(l),triangles:clone(l.triangles)}))};renderInspector();draw();};
  $('#check-mesh').onclick=()=>{const issues=EditorOps.diagnostics(capturePose());modal('Проверка текущей позы',issues.length?`<p>Сжатые или перевёрнутые треугольники. Проверьте эти детали:</p><div class="issue-list">${issues.map(i=>`<button data-issue="${esc(i.id)}">${esc(i.name)} · ${i.count}</button>`).join('')}</div>`:'<p>В текущей позе не найдено сжатых или перевёрнутых треугольников. Просветы, края рисунка и качество мимики проверяются визуально.</p>');$$('[data-issue]').forEach(b=>b.onclick=()=>{S.layer=b.dataset.issue;S.tool='mesh';closeModal();render();});};
  if(!l)return;
  $('#lock-part').onchange=e=>change(()=>l.locked=e.target.checked);
  if($('#polar-rotation'))$('#polar-rotation').onchange=e=>change(()=>l.rotation_mode=e.target.checked?'polar':'legacy');
  if($('#insert-point'))$('#insert-point').onclick=()=>{S.tool='insert';$('#show-mesh').checked=true;toast('Нажмите внутри треугольника. V — движение, M — вершины.');draw();};
  if($('#subdivide-mesh'))$('#subdivide-mesh').onclick=safely(()=>change(()=>{if(l.locked)throw Error('Снимите фиксацию детали');EditorOps.subdivide(l);S.tool='mesh';S.vertex=null;S.selectedVertices=[];}));
  if($('#delete-point'))$('#delete-point').onclick=safely(()=>change(()=>{if(l.locked)throw Error('Снимите фиксацию детали');if(S.vertex==null)throw Error('Выберите точку на холсте');EditorOps.removeVertex(l,S.vertex);S.vertex=null;S.selectedVertices=[];}));
  if($('#soft-radius'))$('#soft-radius').onchange=e=>{S.softRadius=Math.max(0,Math.min(1000,+e.target.value||0));};
  if($('#refine-warp'))$('#refine-warp').onclick=safely(()=>change(()=>{EditorOps.refineWarp(l);S.vertex=null;S.selectedVertices=[];}));
  if($('#replace-art'))$('#replace-art').onclick=()=>$('#replace-file').click();
}
function initEditorUI(){
  $('#new-project').insertAdjacentHTML('afterend','<button id="copy-project" class="square" aria-label="Создать копию проекта" title="Создать копию проекта">⧉</button>');$('#copy-project').onclick=safely(async()=>{await save();const p=await api('save-copy',{project:clone(S.project)});await adopt(p);toast('Открыта самостоятельная копия проекта');});
  const group=$('.tool-group');group.insertAdjacentHTML('beforeend','<button id="hand-tool" aria-label="Перемещать холст (H)" title="Перемещать холст (H)">✥</button>');
  $('#fit').insertAdjacentHTML('beforebegin','<button id="focus-part" aria-label="Приблизить выбранную деталь">Деталь</button><button id="zoom-out" aria-label="Уменьшить">−</button><button id="zoom-in" aria-label="Увеличить">+</button>');
  $('#focus-part').onclick=safely(()=>{const l=layer();if(!l)throw Error('Выберите деталь');const ids=Rig.descendants(l.id,S.project),world=Rig.evaluator(S.project),points=(l.type?S.project.layers.filter(n=>ids.has(n.id)&&!n.mask_only):[l]).flatMap(world);if(!points.length)return;const xs=points.map(v=>v[0]),ys=points.map(v=>v[1]),x=Math.min(...xs),y=Math.min(...ys),w=Math.max(...xs)-x,h=Math.max(...ys)-y,box=canvas.getBoundingClientRect(),scale=Math.max(.02,Math.min(16,(box.width-100)/Math.max(w,80),(box.height-100)/Math.max(h,80)));S.view={scale,x:box.width/2-(x+w/2)*scale,y:box.height/2-(y+h/2)*scale};updateZoom();draw();});
  $('#hand-tool').onclick=()=>{S.tool='hand';render();};$('#zoom-in').onclick=()=>zoomAt(1.3);$('#zoom-out').onclick=()=>zoomAt(1/1.3);
  $('#layer-search').oninput=renderLayers;$('#show-masks').onchange=renderLayers;
  document.body.insertAdjacentHTML('beforeend','<input id="replace-file" type="file" accept=".png,.jpg,.jpeg,.webp" hidden>');
  $('#replace-file').onchange=safely(async e=>{try{const file=e.target.files[0],l=layer();if(!file||!l||l.type)return;if(file.size>64*1024*1024)throw Error('Файл больше 64 МБ');const id=l.id;await save();const content=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});
    const p=await api('replace-asset',{project_id:S.project.id,layer_id:id,revision:S.project._revision,content});checkpoint();S.project=Rig.normalize(p);S.dirty=false;await loadImages();render();toast('Рисунок заменён. Геометрия и формы сохранены; проверьте совмещение.');}finally{e.target.value='';}});
  window.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)||$('#dialog').open)return;if(e.key.toLowerCase()==='h'){S.tool='hand';render();}if(e.key==='Escape'){stopPoseSweep();S.tool='move';draw();}if(e.key==='+'||e.key==='=')zoomAt(1.2);if(e.key==='-')zoomAt(1/1.2);});
}
