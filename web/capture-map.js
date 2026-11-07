'use strict';
const CaptureMap=(()=>{
 const clamp=(x,a,b)=>Math.min(b,Math.max(a,Number.isFinite(x)?x:0));
 function signals(result,aspect=4/3){
  const face=result.faceLandmarks?.[0],categories=result.faceBlendshapes?.[0]?.categories;
  if(!face?.length||!categories?.length)return null;
  const b=Object.fromEntries(categories.map(c=>[c.categoryName,c.score])),get=k=>clamp(b[k]||0,0,1);
  // Landmarks are unmirrored; mirroring affects the preview only. Eyes use subject L/R.
  const a=face[33],z=face[263];
  return {ParamEyeLOpen:1-get('eyeBlinkLeft'),ParamEyeROpen:1-get('eyeBlinkRight'),ParamMouthOpenY:get('jawOpen'),
   ParamEyeBallX:(get('eyeLookOutLeft')-get('eyeLookInLeft')+get('eyeLookInRight')-get('eyeLookOutRight'))/2,
   ParamEyeBallY:(get('eyeLookUpLeft')+get('eyeLookUpRight')-get('eyeLookDownLeft')-get('eyeLookDownRight'))/2,
   ParamBrowLY:get('browOuterUpLeft')+get('browInnerUp')*.5-get('browDownLeft'),ParamBrowRY:get('browOuterUpRight')+get('browInnerUp')*.5-get('browDownRight'),
   // Landmark depth uses the same scale as x. The eye line estimates yaw;
   // use its 2D length so rolling the head does not change the yaw magnitude.
   ParamAngleX:a&&z&&Number.isFinite(a.z)&&Number.isFinite(z.z)?Math.atan2((z.z-a.z)*aspect,Math.hypot((z.x-a.x)*aspect,z.y-a.y))*180/Math.PI:0,
   ParamAngleZ:a&&z?Math.atan2(z.y-a.y,(z.x-a.x)*aspect)*180/Math.PI:0};
 }
 function map(raw,params,{blink=1.5,mouth=2,gaze=2,neutral=null,previous={},smoothing=.35}={}){
  const out={};for(const q of params){if(!(q.id in raw))continue;let v=raw[q.id];
   if(q.id.includes('Eye')&&q.id.endsWith('Open'))v=1-clamp((1-v)*blink,0,1);
   else if(q.id==='ParamMouthOpenY')v=clamp((v-(neutral?.[q.id]||0))*mouth,0,1);
   else if(q.id.startsWith('ParamEyeBall'))v=clamp((v-(neutral?.[q.id]||0))*gaze,-1,1);
   else if(q.id==='ParamAngleZ'||q.id==='ParamAngleX')v-=neutral?.[q.id]||0;
   v=clamp(v,q.min,q.max);const old=previous[q.id];out[q.id]=old===undefined?v:old+(v-old)*(1-clamp(smoothing,0,.9));
  }return out;
 }
 return {signals,map};
})();
if(typeof module!=='undefined')module.exports=CaptureMap;
