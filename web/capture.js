'use strict';
const Capture={active:false,starting:false,epoch:0,stream:null,worker:null,timer:0,raf:0,busy:false,raw:null,neutral:null,values:{},settings:{blink:1.5,mouth:2,gaze:2,smoothing:.35},status:'Камера выключена',lastFace:0,lastTime:-1,lastFrame:0};
function capturePose(){return S.captureValues?{...S.project,parameters:S.project.parameters.map(q=>({...q,value:S.captureValues[q.id]??q.value}))}:S.project;}
function renderCapture(el){
 if((Capture.active||Capture.starting)&&$('#capture-panel'))return;
 el.innerHTML=`<div class="inspector-header"><h2>Проверка захвата</h2><span class="chip">LOCAL</span></div><section class="inspector-section" id="capture-panel"><div class="capture-preview"><video id="camera-video" autoplay muted playsinline></video><canvas id="camera-points" width="640" height="480"></canvas><span id="camera-placeholder">Предпросмотр камеры</span></div><p id="capture-status" role="status">${esc(Capture.status)}</p><div class="field"><label for="camera-device">Камера</label><select id="camera-device"><option value="">Системная камера</option></select></div><button id="camera-start" class="primary wide">Включить камеру</button><button id="camera-stop" class="wide" disabled>Остановить камеру</button><button id="camera-calibrate" class="wide" disabled>Запомнить нейтральную позу</button><p class="hint">Смотрите прямо и расслабьте лицо перед калибровкой. L/R — стороны персонажа. Видео зеркальное; захват сохраняет анатомические стороны.</p><details><summary>Чувствительность</summary>${[['blink','Моргание',.5,3,.1],['mouth','Открытие рта',.5,5,.1],['gaze','Взгляд',.5,5,.1],['smoothing','Сглаживание',0,.9,.05]].map(([id,name,min,max,step])=>`<div class="field"><label for="capture-${id}">${name}</label><input type="range" id="capture-${id}" data-capture-setting="${id}" min="${min}" max="${max}" step="${step}" value="${Capture.settings[id]}"></div>`).join('')}<button id="camera-test" class="wide">Проверить модуль распознавания</button></details><p class="hint">Обработка на этом компьютере. Видео и точки лица не сохраняются и не отправляются в интернет. Режим только для проверки — анимация проекта не перезаписывается.</p></section><section class="inspector-section"><h3>Сигналы персонажа</h3><div id="capture-meters">${S.project.parameters.filter(q=>['ParamEyeLOpen','ParamEyeROpen','ParamMouthOpenY','ParamEyeBallX','ParamEyeBallY','ParamAngleX','ParamAngleZ','ParamBrowLY','ParamBrowRY'].includes(q.id)).map(q=>`<div class="capture-meter"><label>${esc(q.name)}<output data-capture-value="${q.id}">—</output></label><meter data-capture-meter="${q.id}" min="${q.min}" max="${q.max}" value="${q.default}"></meter><small>${allNodes().some(l=>l.keys[q.id]?.length||l.opacity_keys?.[q.id]?.length)?'Связан с моделью':'Нет ключевых форм: сигнал не изменит рисунок'}</small></div>`).join('')||'<p class="hint">У модели нет стандартных параметров захвата. Добавьте их в разделе «Модель».</p>'}</div></section>`;
 $('#camera-start').onclick=()=>startCapture();$('#camera-stop').onclick=()=>stopCapture();
 $('#camera-calibrate').onclick=()=>{if(Capture.raw){Capture.neutral={...Capture.raw};Capture.values={};captureStatus('Нейтральная поза сохранена');}};
 $('#camera-test').onclick=()=>testCaptureRuntime();
 $$('[data-capture-setting]').forEach(i=>i.oninput=()=>Capture.settings[i.dataset.captureSetting]=+i.value);
 listCameraDevices();
}
function captureStatus(text){Capture.status=text;if($('#capture-status'))$('#capture-status').textContent=text;}
async function listCameraDevices(){
 if(!navigator.mediaDevices?.enumerateDevices)return;
 try{const devices=await navigator.mediaDevices.enumerateDevices(),el=$('#camera-device');if(!el)return;const selected=el.value;el.innerHTML='<option value="">Системная камера</option>'+devices.filter(d=>d.kind==='videoinput').map((d,i)=>`<option value="${esc(d.deviceId)}">${esc(d.label||'Камера '+(i+1))}</option>`).join('');el.value=selected;}catch(e){/* Enumeration can be unavailable until permission is granted. */}
}
function loadCaptureWorker(epoch){
 return new Promise((resolve,reject)=>{
  const worker=new Worker('/capture-worker.js');Capture.worker=worker;
  const timeout=setTimeout(()=>{reject(Error('Модуль распознавания не ответил за 45 секунд'));},45000);Capture.timer=timeout;
  worker.onerror=()=>{clearTimeout(timeout);reject(Error('Не удалось запустить модуль распознавания'));};
  worker.onmessage=({data})=>{if(epoch!==Capture.epoch)return;if(data.type==='ready'){clearTimeout(timeout);resolve(worker);}else if(data.type==='error'){clearTimeout(timeout);reject(Error(data.message));}};
  worker.postMessage({type:'init'});
 });
}
async function testCaptureRuntime(){
 if(Capture.active||Capture.starting)return;
 Capture.starting=true;const epoch=++Capture.epoch;captureStatus('Проверка локальной модели…');$('#camera-start').disabled=true;$('#camera-test').disabled=true;$('#camera-stop').disabled=false;
 try{
  const worker=await loadCaptureWorker(epoch);if(epoch!==Capture.epoch)return;
  const blank=new OffscreenCanvas(640,480);blank.getContext('2d').fillRect(0,0,640,480);const frame=blank.transferToImageBitmap();
  const result=await new Promise((resolve,reject)=>{Capture.timer=setTimeout(()=>reject(Error('Нет ответа распознавателя')),15000);worker.onmessage=({data})=>data.type==='result'?resolve(data):reject(Error(data.message||'Ошибка проверки'));worker.postMessage({type:'frame',image:frame,time:performance.now()},[frame]);});
  if(epoch!==Capture.epoch)return;stopCapture();captureStatus(`Модуль готов · ${Math.round(result.ms)} мс. Проверка без камеры пройдена.`);
 }catch(e){if(epoch===Capture.epoch){stopCapture();captureStatus('Ошибка: '+e.message);}}
}
async function startCapture(){
 if(Capture.active||Capture.starting)return;
 if(!navigator.mediaDevices?.getUserMedia){captureStatus('В этом окне камера недоступна. Откройте Лицедей.app или локальный адрес в Safari / Chrome.');return;}
 stop();Capture.starting=true;Capture.neutral=null;Capture.values={};Capture.raw=null;const epoch=++Capture.epoch;
 const device=$('#camera-device').value;$('#camera-start').disabled=true;$('#camera-stop').disabled=false;$('#camera-device').disabled=true;$('#camera-test').disabled=true;captureStatus('Загрузка локального распознавателя…');
 try{
  const worker=await loadCaptureWorker(epoch);if(epoch!==Capture.epoch)return;
  captureStatus('Ожидание разрешения на камеру…');Capture.timer=setTimeout(()=>{if(epoch===Capture.epoch){stopCapture();captureStatus('Разрешение не получено. Нажмите «Включить камеру» и разрешите доступ в системном окне.');}},45000);
  const stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:24,max:30},...(device?{deviceId:{exact:device}}:{facingMode:'user'})},audio:false});
  if(epoch!==Capture.epoch){stream.getTracks().forEach(t=>t.stop());return;}clearTimeout(Capture.timer);
  Capture.stream=stream;const video=$('#camera-video');video.srcObject=stream;await video.play();if(epoch!==Capture.epoch)return;
  Capture.active=true;Capture.starting=false;Capture.lastTime=-1;Capture.lastFrame=0;Capture.lastFace=performance.now();Capture.busy=false;
  stream.getVideoTracks().forEach(t=>t.onended=()=>{stopCapture();captureStatus('Камера отключена. Подключите её и запустите снова.');});
  $('#camera-placeholder').hidden=true;$('#camera-calibrate').disabled=true;captureStatus('Камера включена · найдите лицо в кадре');listCameraDevices();
  worker.onerror=()=>{stopCapture();captureStatus('Распознаватель остановился. Включите камеру снова.');};
  worker.onmessage=({data})=>{
   if(epoch!==Capture.epoch)return;Capture.busy=false;clearTimeout(Capture.timer);
   if(data.type==='error'){stopCapture();captureStatus('Ошибка захвата: '+data.message);return;}
   if(data.type!=='result')return;
   const raw=CaptureMap.signals(data.result,data.aspect);Capture.raw=raw;
   const overlay=$('#camera-points'),g=overlay.getContext('2d');g.clearRect(0,0,640,480);
   if(raw){
    Capture.lastFace=performance.now();Capture.values=CaptureMap.map(raw,S.project.parameters,{...Capture.settings,neutral:Capture.neutral,previous:Capture.values});S.captureValues=Capture.values;
    g.fillStyle='#bcebb6';for(const point of data.result.faceLandmarks[0]){g.beginPath();g.arc(point.x*640,point.y*480,1,0,2*Math.PI);g.fill();}
    captureStatus('Лицо найдено · '+Math.round(data.ms)+' мс на кадр');$('#camera-calibrate').disabled=false;
   }else{captureStatus('Лицо не найдено · смотрите в камеру');$('#camera-calibrate').disabled=true;if(performance.now()-Capture.lastFace>500){Capture.values={};S.captureValues=Object.fromEntries(S.project.parameters.map(q=>[q.id,q.default]));}}
   for(const q of S.project.parameters){const v=S.captureValues?.[q.id];const output=$$('[data-capture-value]').find(el=>el.dataset.captureValue===q.id),meter=$$('[data-capture-meter]').find(el=>el.dataset.captureMeter===q.id);if(output)output.textContent=v===undefined?'—':v.toFixed(2);if(meter&&v!==undefined)meter.value=v;}
   draw();
  };
  const tick=async(now)=>{
   if(epoch!==Capture.epoch||!Capture.active)return;
   Capture.raf=requestAnimationFrame(tick);
   if(Capture.busy||video.readyState<2||video.currentTime===Capture.lastTime||now-Capture.lastFrame<40)return;
   Capture.busy=true;Capture.lastTime=video.currentTime;Capture.lastFrame=now;
   try{const image=await createImageBitmap(video);if(epoch!==Capture.epoch){image.close();return;}worker.postMessage({type:'frame',image,time:now},[image]);Capture.timer=setTimeout(()=>{stopCapture();captureStatus('Захват не отвечает. Камера остановлена.');},10000);}catch(e){if(epoch===Capture.epoch){stopCapture();captureStatus('Не удалось прочитать кадр: '+e.message);}}
  };Capture.raf=requestAnimationFrame(tick);
 }catch(e){if(epoch!==Capture.epoch)return;stopCapture();const messages={NotAllowedError:'Доступ к камере не разрешён. Разрешите его для Лицедей в настройках конфиденциальности macOS и в окне браузера.',NotFoundError:'Камера не найдена. Подключите камеру и попробуйте снова.',NotReadableError:'Камера занята или недоступна. Закройте другие приложения, использующие её.'};captureStatus(messages[e.name]||'Не удалось включить камеру: '+e.message);}
}
function stopCapture(){
 ++Capture.epoch;Capture.active=false;Capture.starting=false;cancelAnimationFrame(Capture.raf);clearTimeout(Capture.timer);
 Capture.worker?.terminate();Capture.worker=null;Capture.stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});Capture.stream=null;Capture.busy=false;Capture.raw=null;Capture.values={};S.captureValues=null;
 if($('#camera-video')){$('#camera-video').srcObject=null;$('#camera-points').getContext('2d').clearRect(0,0,640,480);$('#camera-placeholder').hidden=false;$('#camera-start').disabled=false;$('#camera-test').disabled=false;$('#camera-stop').disabled=true;$('#camera-calibrate').disabled=true;$('#camera-device').disabled=false;}
 captureStatus('Камера выключена');if(S.project)draw();
}
window.addEventListener('pagehide',stopCapture);
document.addEventListener('visibilitychange',()=>{if(document.hidden&&(Capture.active||Capture.starting))stopCapture();});
window.addEventListener('keydown',e=>{if(e.key==='Escape'&&(Capture.active||Capture.starting))stopCapture();});
