import json
import subprocess
import unittest

class CaptureTests(unittest.TestCase):
 def run_js(self,code):
  return json.loads(subprocess.check_output(['node','-e',"const C=require('./web/capture-map.js');"+code],text=True))
 def test_no_face_and_anatomical_blink(self):
  value=self.run_js("const face=Array.from({length:478},()=>({x:0,y:0}));face[263]={x:1,y:0};const r=C.signals({faceLandmarks:[face],faceBlendshapes:[{categories:[{categoryName:'eyeBlinkLeft',score:1},{categoryName:'eyeBlinkRight',score:0},{categoryName:'jawOpen',score:.4}]}]});console.log(JSON.stringify([C.signals({}),r]));")
  self.assertIsNone(value[0]);self.assertEqual(value[1]['ParamEyeLOpen'],0);self.assertEqual(value[1]['ParamEyeROpen'],1);self.assertEqual(value[1]['ParamMouthOpenY'],.4)
 def test_clamp_smoothing_calibration_and_no_mutation(self):
  value=self.run_js("const p=[{id:'ParamAngleZ',min:-12,max:12,value:0},{id:'ParamMouthOpenY',min:0,max:1,value:0},{id:'Custom',min:0,max:1,value:0}];const before=JSON.stringify(p);const raw={ParamAngleZ:60,ParamMouthOpenY:.4};const mapped=C.map(raw,p,{neutral:{ParamAngleZ:5,ParamMouthOpenY:.1},previous:{ParamAngleZ:0},smoothing:.5});console.log(JSON.stringify({mapped,unchanged:JSON.stringify(p)===before}));")
  self.assertEqual(value['mapped']['ParamAngleZ'],6);self.assertAlmostEqual(value['mapped']['ParamMouthOpenY'],.6);self.assertNotIn('Custom',value['mapped']);self.assertTrue(value['unchanged'])
 def test_invalid_measurement_is_finite(self):
  value=self.run_js("console.log(JSON.stringify(C.map({ParamAngleZ:NaN},[{id:'ParamAngleZ',min:-12,max:12}],{smoothing:0}))); ")
  self.assertEqual(value['ParamAngleZ'],0)
 def test_gaze_direction_and_roll_account_for_aspect_ratio(self):
  value=self.run_js("const face=Array.from({length:478},()=>({x:0,y:0}));face[263]={x:.5,y:.5*(4/3)*Math.tan(Math.PI/6)};const r=C.signals({faceLandmarks:[face],faceBlendshapes:[{categories:[{categoryName:'eyeLookOutLeft',score:1},{categoryName:'eyeLookInRight',score:1}]}]},4/3);console.log(JSON.stringify(r));")
  self.assertEqual(value['ParamEyeBallX'],1);self.assertAlmostEqual(value['ParamAngleZ'],30)
 def test_stop_releases_devices_worker_and_transient_pose(self):
  value=self.run_js("const fs=require('fs'),vm=require('vm');let stopped=0,terminated=0;const context={result:null,S:{project:null,captureValues:{ParamEyeLOpen:0}},window:{addEventListener(){}},document:{addEventListener(){}},cancelAnimationFrame(){},clearTimeout(){},$:()=>null};vm.createContext(context);vm.runInContext(fs.readFileSync('./web/capture.js','utf8')+`\\nCapture.active=true;Capture.starting=true;Capture.worker={terminate(){terminatedFlag=true}};Capture.stream={getTracks(){return [{stop(){stoppedFlag=true},onended:()=>{}}]}};stopCapture();result={active:Capture.active,starting:Capture.starting,stream:Capture.stream,worker:Capture.worker,pose:S.captureValues,stopped:stoppedFlag,terminated:terminatedFlag};`,Object.assign(context,{stoppedFlag:false,terminatedFlag:false}));console.log(JSON.stringify(context.result));")
  self.assertFalse(value['active']);self.assertFalse(value['starting']);self.assertIsNone(value['stream']);self.assertIsNone(value['worker']);self.assertIsNone(value['pose']);self.assertTrue(value['stopped']);self.assertTrue(value['terminated'])
 def test_yaw_depth_direction_and_calibration(self):
  value=self.run_js("const f=Array.from({length:478},()=>({x:0,y:0,z:0}));f[33]={x:.3,y:.5,z:-.05};f[263]={x:.7,y:.5,z:.05};const r=C.signals({faceLandmarks:[f],faceBlendshapes:[{categories:[{categoryName:'jawOpen',score:0}]}]});const p=[{id:'ParamAngleX',min:-20,max:20},{id:'ParamBodyAngleX',min:-15,max:15}];console.log(JSON.stringify([r.ParamAngleX,C.map(r,p,{neutral:{ParamAngleX:4},smoothing:0})]));")
  self.assertAlmostEqual(value[0],14.036243467926479)
  self.assertAlmostEqual(value[1]['ParamAngleX'],10.036243467926479)
  self.assertNotIn('ParamBodyAngleX',value[1])
