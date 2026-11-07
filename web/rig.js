'use strict';
// Pure geometry and curve functions are shared by the editor and Node tests.
const Rig = (() => {
  function normalize(p){p.deformers??=[];if(!p.tracks){p.tracks=Object.fromEntries(p.parameters.map(q=>[q.id,p.timeline.map(f=>({time:f.time,value:f.values[q.id],interpolation:'linear'}))]));}p.timeline=[];p.loop??=true;return p;}
  function delta(node,param){let keys=[...(node.keys[param.id]||[])];const zero=()=>node.vertices.map(()=>[0,0]);if(!keys.length)return zero();if(!keys.some(k=>k.value===param.default))keys.push({value:param.default,delta:zero()});keys.sort((a,b)=>a.value-b.value);const a=[...keys].reverse().find(k=>k.value<=param.value)||keys[0],b=keys.find(k=>k.value>=param.value)||keys.at(-1),t=a.value===b.value?0:(param.value-a.value)/(b.value-a.value);return a.delta.map((v,i)=>v.map((x,j)=>x*(1-t)+b.delta[i][j]*t));}
  function opacityFactor(node,q){const keys=[...(node.opacity_keys?.[q.id]||[])];if(!keys.length)return 1;if(!keys.some(k=>k.value===q.default))keys.push({value:q.default,opacity:1});keys.sort((a,b)=>a.value-b.value);const a=[...keys].reverse().find(k=>k.value<=q.value)||keys[0],b=keys.find(k=>k.value>=q.value)||keys.at(-1),t=a.value===b.value?0:(q.value-a.value)/(b.value-a.value);return a.opacity*(1-t)+b.opacity*t;}
  function opacity(node,params){return Math.max(0,Math.min(1,params.reduce((v,q)=>v*opacityFactor(node,q),node.opacity)));}
  function bindPoint(node,[x,y]){const [a,b,c,d,e,f]=node.bind||[1,0,0,1,0,0];return [a*x+c*y+e,b*x+d*y+f];}
  function polar(node,params){
    const [[cx,cy],[hx,hy]]=node.vertices,length=Math.hypot(hx-cx,hy-cy),angle=Math.atan2(hy-cy,hx-cx);
    if(length<1e-8)return local({...node,rotation_mode:'legacy'},params);
    let ox=cx,oy=cy,outAngle=angle,outLength=length;
    for(const q of params){
      const keys=[...(node.keys[q.id]||[])];if(!keys.length)continue;
      if(!keys.some(k=>k.value===q.default))keys.push({value:q.default,delta:[[0,0],[0,0]]});
      keys.sort((a,b)=>a.value-b.value);const forms=[];
      for(const k of keys){const [[dx,dy],[ex,ey]]=k.delta,vx=hx+ex-cx-dx,vy=hy+ey-cy-dy;let a=Math.atan2(vy,vx)-angle;
        while(a>Math.PI)a-=2*Math.PI;while(a< -Math.PI)a+=2*Math.PI;
        if(forms.length){while(a-forms.at(-1)[3]>Math.PI)a-=2*Math.PI;while(a-forms.at(-1)[3]< -Math.PI)a+=2*Math.PI;}
        forms.push([k.value,dx,dy,a,Math.hypot(vx,vy)/length]);}
      const a=[...forms].reverse().find(k=>k[0]<=q.value)||forms[0],b=forms.find(k=>k[0]>=q.value)||forms.at(-1),t=a[0]===b[0]?0:(q.value-a[0])/(b[0]-a[0]),v=a.slice(1).map((x,i)=>x*(1-t)+b[i+1]*t);
      ox+=v[0];oy+=v[1];outAngle+=v[2];outLength*=v[3];
    }
    const cs=combinationDelta(node,params);return [[ox,oy],[ox+outLength*Math.cos(outAngle),oy+outLength*Math.sin(outAngle)]].map((v,i)=>v.map((x,j)=>x+cs[i][j]));
  }
  function local(node,params){if(node.type==='rotation'&&node.rotation_mode==='polar')return polar(node,params);const vs=node.vertices.map(v=>[...v]);for(const q of params){const ds=delta(node,q);vs.forEach((v,i)=>{v[0]+=ds[i][0];v[1]+=ds[i][1];});}const cs=combinationDelta(node,params);vs.forEach((v,i)=>{v[0]+=cs[i][0];v[1]+=cs[i][1];});return vs;}
  function combinationDelta(node,params,only=null){const result=node.vertices.map(()=>[0,0]);for(const combo of node.combinations||[]){if(only&&combo!==only)continue;const ranges=combo.parameters.map((pid,axis)=>{const q=params.find(q=>q.id===pid),anchors=[...new Set([q.min,q.default,q.max,...combo.keys.map(k=>k.values[axis])])].sort((a,b)=>a-b),a=[...anchors].reverse().find(v=>v<=q.value)??anchors[0],b=anchors.find(v=>v>=q.value)??anchors.at(-1),t=a===b?0:(q.value-a)/(b-a);return [[a,1-t],[b,t]];});for(const [x,wx] of ranges[0])for(const [y,wy] of ranges[1]){const k=combo.keys.find(k=>k.values[0]===x&&k.values[1]===y);if(k)result.forEach((v,i)=>{v[0]+=k.delta[i][0]*wx*wy;v[1]+=k.delta[i][1]*wx*wy;});}}return result;}
  function transform(d,[x,y],params){const vs=local(d,params);if(d.type==='rotation'){const [[px,py],[hx,hy]]=d.rest||d.vertices,[[cx,cy],[tx,ty]]=vs,bx=hx-px,by=hy-py,den=bx*bx+by*by,a=((tx-cx)*bx+(ty-cy)*by)/den,b=((ty-cy)*bx-(tx-cx)*by)/den;return bindPoint(d,[cx+a*(x-px)-b*(y-py),cy+b*(x-px)+a*(y-py)]);}const [bx,by,w,h]=d.bounds,n=d.divisions,fx=(x-bx)/w*n,fy=(y-by)/h*n,col=Math.max(0,Math.min(n-1,Math.floor(fx))),row=Math.max(0,Math.min(n-1,Math.floor(fy))),u=fx-col,v=fy-row,ids=[row*(n+1)+col,row*(n+1)+col+1,(row+1)*(n+1)+col,(row+1)*(n+1)+col+1],weights=[(1-u)*(1-v),u*(1-v),(1-u)*v,u*v];return bindPoint(d,[0,1].map(a=>ids.reduce((sum,i,j)=>sum+vs[i][a]*weights[j],0)));}
  function chain(node,p){const list=[];let parent=node.parent;while(parent){const d=p.deformers.find(d=>d.id===parent);if(!d||list.includes(d))throw Error('Повреждена иерархия');list.push(d);parent=d.parent;}return list;}
  function toWorld(node,point,p){point=bindPoint(node,point);for(const d of chain(node,p))point=transform(d,point,p.parameters);return point;}
  function world(node,p){return local(node,p.parameters).map(v=>toWorld(node,v,p));}
  function inverse(d,target,params){let x=[...target];for(let i=0;i<20;i++){const f=transform(d,x,params),ex=target[0]-f[0],ey=target[1]-f[1];if(Math.hypot(ex,ey)<.0001)return x;const h=.01,fx=transform(d,[x[0]+h,x[1]],params),fy=transform(d,[x[0],x[1]+h],params),a=(fx[0]-f[0])/h,b=(fx[1]-f[1])/h,c=(fy[0]-f[0])/h,e=(fy[1]-f[1])/h,det=a*e-b*c;if(Math.abs(det)<1e-8)break;x[0]+=(e*ex-c*ey)/det;x[1]+=(-b*ex+a*ey)/det;}throw Error('Родительский деформер сжат или перевёрнут. Исправьте его форму перед редактированием дочернего объекта.');}
  function toLocal(node,point,p){for(const d of chain(node,p).reverse())point=inverse(d,point,p.parameters);const [a,b,c,d,e,f]=node.bind||[1,0,0,1,0,0],det=a*d-b*c,x=point[0]-e,y=point[1]-f;return [(d*x-c*y)/det,(a*y-b*x)/det];}
  function sample(keys,t,def){if(!keys?.length)return def;keys=[...keys].sort((a,b)=>a.time-b.time);const a=[...keys].reverse().find(k=>k.time<=t)||keys[0],b=keys.find(k=>k.time>=t)||keys.at(-1);let v=a.time===b.time?0:(t-a.time)/(b.time-a.time);if(a.interpolation==='step')v=0;else if(a.interpolation==='smooth')v=v*v*(3-2*v);return a.value*(1-v)+b.value*v;}
  function descendants(id,p){const found=new Set([id]);let changed=true;while(changed){changed=false;for(const n of [...p.layers,...p.deformers])if(found.has(n.parent)&&!found.has(n.id)){found.add(n.id);changed=true;}}return found;}
  function deformer(type,name,bounds,parent=null){const [x,y,w,h]=bounds,d={id:crypto.randomUUID(),type,name,parent,keys:{},vertices:[],bounds:[...bounds],divisions:2};if(type==='rotation')d.rotation_mode='polar';if(type==='rotation')d.vertices=[[x+w/2,y+h/2],[x+w/2+Math.max(20,w/3),y+h/2]];else for(let r=0;r<=2;r++)for(let c=0;c<=2;c++)d.vertices.push([x+w*c/2,y+h*r/2]);d.rest=d.vertices.map(v=>[...v]);return d;}
  function evaluator(p){
    const forms=new Map(),nodes=new Map(p.deformers.map(d=>[d.id,d]));
    const form=n=>{if(!forms.has(n.id))forms.set(n.id,local(n,p.parameters));return forms.get(n.id);};
    const transformCached=(d,[x,y])=>{
      const vs=form(d);
      if(d.type==='rotation'){const [[px,py],[hx,hy]]=d.rest||d.vertices,[[cx,cy],[tx,ty]]=vs,bx=hx-px,by=hy-py,den=bx*bx+by*by,a=((tx-cx)*bx+(ty-cy)*by)/den,b=((ty-cy)*bx-(tx-cx)*by)/den;return bindPoint(d,[cx+a*(x-px)-b*(y-py),cy+b*(x-px)+a*(y-py)]);}
      const [bx,by,w,h]=d.bounds,n=d.divisions,fx=(x-bx)/w*n,fy=(y-by)/h*n,c=Math.max(0,Math.min(n-1,Math.floor(fx))),r=Math.max(0,Math.min(n-1,Math.floor(fy))),u=fx-c,v=fy-r,ids=[r*(n+1)+c,r*(n+1)+c+1,(r+1)*(n+1)+c,(r+1)*(n+1)+c+1],weights=[(1-u)*(1-v),u*(1-v),(1-u)*v,u*v];
      return bindPoint(d,[0,1].map(a=>ids.reduce((s,i,j)=>s+vs[i][a]*weights[j],0)));
    };
    return n=>{let vs=form(n).map(v=>bindPoint(n,v)),parent=n.parent;while(parent){const d=nodes.get(parent);if(!d)throw Error('Повреждена иерархия');vs=vs.map(v=>transformCached(d,v));parent=d.parent;}return vs;};
  }
  return {evaluator,bindPoint,opacity,opacityFactor,normalize,delta,combinationDelta,local,transform,chain,toWorld,world,toLocal,sample,descendants,deformer};
})();
if(typeof module!=='undefined')module.exports=Rig;

class PhysicsPreview {
  constructor(project){
    this.groups=(project.physics||[]).filter(g=>g.enabled!==false);this.params=project.parameters;this.frames=[];
    const states=this.groups.map(()=>[0,0]),count=Math.ceil(project.duration*120);
    for(let step=0;step<=count;step++){
      const t=step/120,values=Object.fromEntries(this.params.map(q=>[q.id,Rig.sample(project.tracks[q.id],t,q.default)]));
      this.groups.forEach((g,i)=>{const q=this.params.find(q=>q.id===g.input),v=values[q.id]-q.default,den=v>=0?q.max-q.default:q.default-q.min,force=v/Math.max(den,1e-8)*g.strength,omega=2*Math.PI*g.frequency,s=states[i];if(step){s[1]+=(omega*omega*(force-s[0])-2*g.damping*omega*s[1])/120;s[0]+=s[1]/120;}});
      this.frames.push(states.map(s=>s[0]));
    }
  }
  apply(values,t){const a=Math.min(this.frames.length-1,Math.floor(t*120)),b=Math.min(a+1,this.frames.length-1),f=t*120-a;this.groups.forEach((g,i)=>{const q=this.params.find(q=>q.id===g.output),x=this.frames[a][i]*(1-f)+this.frames[b][i]*f,span=x>=0?q.max-q.default:q.default-q.min;values[q.id]=Math.max(q.min,Math.min(q.max,values[q.id]+x*span));});return values;}
}
if(typeof module!=='undefined')module.exports.PhysicsPreview=PhysicsPreview;
