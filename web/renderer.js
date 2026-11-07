'use strict';
// GPU rasterization shares triangle edges exactly, avoiding Canvas2D clip seams.
class MeshRenderer {
  constructor(){
    this.canvas=document.createElement('canvas');
    const gl=this.gl=this.canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:false,preserveDrawingBuffer:true});
    if(!gl)throw Error('WebGL недоступен');
    const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;};
    const program=this.program=gl.createProgram();
    gl.attachShader(program,shader(gl.VERTEX_SHADER,'attribute vec2 position; attribute vec2 uv; uniform vec2 resolution; varying vec2 texcoord; void main(){vec2 clip=position/resolution*2.0-1.0;gl_Position=vec4(clip.x,-clip.y,0.0,1.0);texcoord=uv;}'));
    gl.attachShader(program,shader(gl.FRAGMENT_SHADER,'precision mediump float; varying vec2 texcoord; uniform sampler2D image; uniform float opacity; void main(){gl_FragColor=texture2D(image,texcoord)*opacity;}'));
    gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw Error('Не удалось создать рендерер');
    gl.useProgram(program);this.position=gl.getAttribLocation(program,'position');this.uv=gl.getAttribLocation(program,'uv');this.resolution=gl.getUniformLocation(program,'resolution');this.opacity=gl.getUniformLocation(program,'opacity');
    this.buffer=gl.createBuffer();this.textures=new Map();
    gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);
    this.canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();this.lost=true;});
  }
  render(project,images,deform){
    if(this.lost)throw Error('Графический контекст потерян. Перезапустите окно редактора.');
    const gl=this.gl;
    if(this.canvas.width!==project.width||this.canvas.height!==project.height){this.canvas.width=project.width;this.canvas.height=project.height;}
    gl.viewport(0,0,project.width,project.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.useProgram(this.program);gl.uniform2f(this.resolution,project.width,project.height);
    gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);gl.enableVertexAttribArray(this.position);gl.enableVertexAttribArray(this.uv);gl.vertexAttribPointer(this.position,2,gl.FLOAT,false,16,0);gl.vertexAttribPointer(this.uv,2,gl.FLOAT,false,16,8);
    for(const l of project.layers){
      if(!l.visible||!images.has(l.asset))continue;
      let texture=this.textures.get(l.asset);
      if(!texture){texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,images.get(l.asset));this.textures.set(l.asset,texture);}
      gl.bindTexture(gl.TEXTURE_2D,texture);gl.uniform1f(this.opacity,Rig.opacity(l,project.parameters));
      const vertices=deform(l),data=[];for(const tri of l.triangles)for(const i of tri)data.push(...vertices[i],...l.uv[i]);
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.DYNAMIC_DRAW);gl.drawArrays(gl.TRIANGLES,0,data.length/4);
    }
    return this.canvas;
  }
}

// Both renderers feed the same mask compositor, including the non-WebGL fallback.
class SoftwareMeshRenderer {
  constructor(){this.canvas=document.createElement('canvas');}
  render(p,images,deform){
    const c=this.canvas;if(c.width!==p.width||c.height!==p.height){c.width=p.width;c.height=p.height;}
    const g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);
    for(const l of p.layers){if(!l.visible||!images.has(l.asset))continue;const image=images.get(l.asset),vs=deform(l);g.globalAlpha=Rig.opacity(l,p.parameters);
      for(const tri of l.triangles){const src=tri.map(i=>[l.uv[i][0]*(image.naturalWidth||image.width),l.uv[i][1]*(image.naturalHeight||image.height)]),dst=tri.map(i=>vs[i]);
        const [[u0,v0],[u1,v1],[u2,v2]]=src,det=u0*(v1-v2)+u1*(v2-v0)+u2*(v0-v1);if(Math.abs(det)<1e-8)continue;
        const coeff=a=>[(a[0]*(v1-v2)+a[1]*(v2-v0)+a[2]*(v0-v1))/det,(a[0]*(u2-u1)+a[1]*(u0-u2)+a[2]*(u1-u0))/det,(a[0]*(u1*v2-u2*v1)+a[1]*(u2*v0-u0*v2)+a[2]*(u0*v1-u1*v0))/det];
        const [a,c,e]=coeff(dst.map(v=>v[0])),[b,d,f]=coeff(dst.map(v=>v[1]));g.save();g.beginPath();dst.forEach((v,i)=>i?g.lineTo(...v):g.moveTo(...v));g.closePath();g.clip();g.transform(a,b,c,d,e,f);g.drawImage(image,0,0);g.restore();}
    }g.globalAlpha=1;return c;
  }
}
class SceneRenderer {
  constructor(){try{this.mesh=new MeshRenderer();}catch(e){this.mesh=new SoftwareMeshRenderer();}this.canvas=document.createElement('canvas');this.surfaces=[];}
  render(p,images,deform){
    if(this.mesh.lost)this.mesh=new SoftwareMeshRenderer();
    if(this.mesh.textures){const used=new Set(p.layers.map(l=>l.asset));for(const [id,t] of this.mesh.textures)if(!used.has(id)){this.mesh.gl.deleteTexture(t);this.mesh.textures.delete(id);}}
    if(!p.layers.some(l=>l.masks?.length)){for(const c of this.surfaces){c.width=0;c.height=0;}this.surfaces=[];return this.mesh.render({...p,layers:p.layers.filter(l=>!l.mask_only)},images,deform);}
    const free=[...this.surfaces],busy=new Set(),surface=()=>{const c=free.pop()||document.createElement('canvas');if(!this.surfaces.includes(c))this.surfaces.push(c);busy.add(c);if(c.width!==p.width||c.height!==p.height){c.width=p.width;c.height=p.height;}else c.getContext('2d').clearRect(0,0,c.width,c.height);return c;};
    const release=c=>{if(busy.delete(c))free.push(c);};
    if(this.canvas.width!==p.width||this.canvas.height!==p.height){this.canvas.width=p.width;this.canvas.height=p.height;}
    const ctx=this.canvas.getContext('2d');ctx.clearRect(0,0,p.width,p.height);
    const lookup=new Map(p.layers.map(l=>[l.id,l])),refs=new Map(),seen=new Set(),cache=new Map();
    const reference=id=>refs.set(id,(refs.get(id)||0)+1);
    const visit=l=>{if(seen.has(l.id))return;seen.add(l.id);for(const id of l.masks||[]){reference(id);visit(lookup.get(id));}};
    for(const l of p.layers)if(l.visible&&!l.mask_only&&l.masks?.length){reference(l.id);visit(l);}
    const consume=(id,c)=>{const count=(refs.get(id)||1)-1;refs.set(id,count);if(count===0){cache.delete(id);release(c);}};
    const raster=l=>{
      if(cache.has(l.id))return cache.get(l.id);
      const c=surface(),g=c.getContext('2d');g.drawImage(this.mesh.render({...p,layers:[{...l,visible:true}]},images,deform),0,0);
      if(l.masks?.length){const m=surface(),mg=m.getContext('2d');for(const id of l.masks){const src=raster(lookup.get(id));mg.drawImage(src,0,0);consume(id,src);}g.globalCompositeOperation=l.mask_invert?'destination-out':'destination-in';g.drawImage(m,0,0);g.globalCompositeOperation='source-over';release(m);}
      cache.set(l.id,c);return c;
    };
    let batch=[];const flush=()=>{if(batch.length){ctx.drawImage(this.mesh.render({...p,layers:batch},images,deform),0,0);batch=[];}};
    for(const l of p.layers)if(l.visible&&!l.mask_only){if(l.masks?.length){flush();const c=raster(l);ctx.drawImage(c,0,0);consume(l.id,c);}else batch.push(l);}flush();
    return this.canvas;
  }
}
