'use strict';
self.exports={};
let detector;
self.onmessage=async({data})=>{
 try{
  if(data.type==='init'){
   importScripts('/vendor/mediapipe/vision_bundle.cjs');
   const vision=await exports.FilesetResolver.forVisionTasks('/vendor/mediapipe/wasm');
   detector=await exports.FaceLandmarker.createFromOptions(vision,{baseOptions:{modelAssetPath:'/vendor/mediapipe/face_landmarker.task',delegate:'CPU'},canvas:new OffscreenCanvas(640,480),runningMode:'VIDEO',numFaces:1,outputFaceBlendshapes:true});
   self.postMessage({type:'ready'});
  }else if(data.type==='frame'){
   try{const start=performance.now();const result=detector.detectForVideo(data.image,data.time);self.postMessage({type:'result',result,aspect:data.image.width/data.image.height,ms:performance.now()-start});}finally{data.image.close();}
  }
 }catch(e){self.postMessage({type:'error',message:String(e.message||e)});}
};
