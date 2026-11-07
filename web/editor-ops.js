'use strict';
// Document operations are independent of the UI and never reference a character.
const EditorOps = (() => {
  const R = typeof module !== 'undefined' ? require('./rig.js') : Rig;
  const identity = [1,0,0,1,0,0];
  const copy = x => JSON.parse(JSON.stringify(x));
  function multiply(a,b) {
    return [a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]];
  }
  function invert(m) {
    const [a,b,c,d,e,f]=m,det=a*d-b*c;
    if(Math.abs(det)<1e-10)throw Error('Привязка сжата: восстановите форму перед переносом.');
    return [d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det];
  }
  function apply(m,[x,y]) {return [m[0]*x+m[2]*y+m[4],m[1]*x+m[3]*y+m[5]];}
  function affine(d,p) {
    const o=R.transform(d,[0,0],p.parameters),x=R.transform(d,[1,0],p.parameters),y=R.transform(d,[0,1],p.parameters);
    const m=[x[0]-o[0],x[1]-o[1],y[0]-o[0],y[1]-o[1],...o];
    if(d.type==='warp'){
      const [x,y,w,h]=d.bounds,n=d.divisions;
      for(let r=0;r<=n;r++)for(let c=0;c<=n;c++){
        const v=[x+w*c/n,y+h*r/n],a=R.transform(d,v,p.parameters),b=apply(m,v);
        if(Math.hypot(a[0]-b[0],a[1]-b[1])>1e-4)throw Error('Сейчас родитель изогнут. Верните параметры в нейтраль перед перепривязкой: это сохранит форму и ключи.');
      }
    }
    invert(m);return m;
  }
  function parentMatrix(n,p) {let m=identity;for(const d of R.chain(n,p))m=multiply(affine(d,p),m);return m;}
  function reparent(p,id,parent) {
    const n=[...p.layers,...p.deformers].find(n=>n.id===id);
    if(!n)throw Error('Объект не найден');
    if(parent&&(!p.deformers.some(d=>d.id===parent)||R.descendants(id,p).has(parent)))throw Error('Недопустимый родитель');
    const old=parentMatrix(n,p),next=parentMatrix({...n,parent},p);
    const targets=[n,...p.layers.filter(m=>m.mask_only&&m.parent===n.parent&&(n.masks||[]).includes(m.id)&&p.layers.filter(l=>(l.masks||[]).includes(m.id)).length===1)];
    const compensation=multiply(invert(next),old);
    for(const target of targets){target.bind=multiply(compensation,target.bind||identity);target.parent=parent||null;}
  }
  function removeDeformer(p,id) {
    // Work on a copy so a non-affine child cannot leave a partially changed tree.
    const work=copy(p),d=work.deformers.find(d=>d.id===id);
    if(!d)throw Error('Деформер не найден');
    for(const n of [...work.layers,...work.deformers].filter(n=>n.parent===id))reparent(work,n.id,d.parent||null);
    work.deformers=work.deformers.filter(n=>n.id!==id);
    p.layers=work.layers;p.deformers=work.deformers;
  }
  function splitTriangle(n,index,weights=[1/3,1/3,1/3]) {
    if(n.type)throw Error('Выберите рисуемый слой');
    if(n.vertices.length>=1000||n.triangles.length+2>2000)throw Error('Достигнут предел сетки');
    const tri=n.triangles[index];if(!tri||weights.some(w=>!Number.isFinite(w)||w<=1e-5)||Math.abs(weights.reduce((a,b)=>a+b)-1)>1e-5)throw Error('Выберите точку внутри треугольника');
    const sample=vs=>[0,1].map(j=>tri.reduce((v,i,k)=>v+vs[i][j]*weights[k],0));
    const i=n.vertices.length;
    for(const vs of [n.vertices,n.uv,...Object.values(n.keys).flat().map(k=>k.delta),...(n.combinations||[]).flatMap(c=>c.keys.map(k=>k.delta))])vs.push(sample(vs));
    const [a,b,c]=tri;n.triangles.splice(index,1,[a,b,i],[b,c,i],[c,a,i]);return i;
  }
  function subdivide(n) {
    if(n.type)throw Error('Выберите рисуемый слой');
    const count=n.triangles.length;if(n.vertices.length+count>1000||count*3>2000)throw Error('Недостаточно места для деления всех треугольников');
    // Reverse iteration keeps the original triangle indices valid.
    for(let i=count-1;i>=0;i--)splitTriangle(n,i);
  }
  function weights(point,tri) {
    const [[ax,ay],[bx,by],[cx,cy]]=tri,[x,y]=point,det=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy);
    if(Math.abs(det)<1e-10)return null;
    const a=((by-cy)*(x-cx)+(cx-bx)*(y-cy))/det,b=((cy-ay)*(x-cx)+(ax-cx)*(y-cy))/det;
    const w=[a,b,1-a-b];return w.every(v=>v>1e-5)?w:null;
  }
  function insertAt(n,p,point) {
    const vs=R.world(n,p);
    for(let i=0;i<n.triangles.length;i++){const w=weights(point,n.triangles[i].map(j=>vs[j]));if(w)return splitTriangle(n,i,w);}
    throw Error('Нажмите внутри треугольника, немного дальше от ребра.');
  }
  function removeVertex(n,index) {
    // Safely reverse an interior three-triangle split without inventing a boundary.
    const touching=n.triangles.filter(t=>t.includes(index));
    const ring=[...new Set(touching.flat().filter(i=>i!==index))];
    if(touching.length!==3||ring.length!==3)throw Error('Можно удалить внутреннюю точку с тремя соседями. Границы сетки сохраняются.');
    const edges=touching.map(t=>{const j=t.indexOf(index);return [t[(j+1)%3],t[(j+2)%3]];});
    const a=edges[0],b=edges.find(e=>e[0]===a[1]);
    if(!b||!edges.some(e=>e[0]===b[1]&&e[1]===a[0]))throw Error('Соседние треугольники не образуют замкнутый контур');
    n.triangles=n.triangles.filter(t=>!t.includes(index));n.triangles.push([a[0],a[1],b[1]]);
    for(const vs of [n.vertices,n.uv,...Object.values(n.keys).flat().map(k=>k.delta),...(n.combinations||[]).flatMap(c=>c.keys.map(k=>k.delta))])vs.splice(index,1);
    n.triangles=n.triangles.map(t=>t.map(i=>i>index?i-1:i));
  }
  function diagnostics(p) {
    const issues=[];
    for(const n of p.layers){const vs=R.world(n,p),area=(points,t)=>{const [a,b,c]=t.map(i=>points[i]);return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);};
      const bad=n.triangles.filter(t=>Math.abs(area(vs,t))<1e-5||area(vs,t)*area(n.vertices,t)<0).length;
      if(bad)issues.push({id:n.id,name:n.name,count:bad});
    }return issues;
  }
  function refineWarp(n) {
    if(n.type!=='warp'||n.divisions*2>8)throw Error('Решётку можно уплотнить до 8 × 8 ячеек');
    const old=n.divisions,size=old*2;
    const sample=vs=>{const out=[];for(let r=0;r<=size;r++)for(let c=0;c<=size;c++){
      const x=c/2,y=r/2,col=Math.min(old-1,Math.floor(x)),row=Math.min(old-1,Math.floor(y)),u=x-col,v=y-row,ids=[row*(old+1)+col,row*(old+1)+col+1,(row+1)*(old+1)+col,(row+1)*(old+1)+col+1],w=[(1-u)*(1-v),u*(1-v),(1-u)*v,u*v];
      out.push([0,1].map(j=>ids.reduce((sum,i,k)=>sum+vs[i][j]*w[k],0)));}return out;};
    n.vertices=sample(n.vertices);if(n.rest)n.rest=sample(n.rest);
    for(const k of [...Object.values(n.keys).flat(),...(n.combinations||[]).flatMap(c=>c.keys)])k.delta=sample(k.delta);
    n.divisions=size;
  }
  return {multiply,invert,apply,reparent,removeDeformer,splitTriangle,subdivide,insertAt,removeVertex,diagnostics,refineWarp};
})();
if(typeof module!=='undefined')module.exports=EditorOps;
