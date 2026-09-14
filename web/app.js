'use strict';
const $=id=>document.getElementById(id),world=$('world'),ctx=world.getContext('2d');
let state=null,selected=null,flies=[],generation=0,bar=0,positions=[],visualTime=0,lastFrame=0,lastRender='';
const number=(n,d=2)=>Number(n).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const text=(id,value)=>$(id).textContent=value;
function element(tag,content,cls){const e=document.createElement(tag);e.textContent=content;if(cls)e.className=cls;return e;}
async function request(path,options){const response=await fetch(path,options);if(!response.ok)throw Error('HTTP '+response.status);return response.json();}
async function poll(){try{const next=await request('/api/state'+(state?'?brief=1':''));state={...state,...next};update();text('connection','● LOCAL ENGINE CONNECTED');text('error','');}catch(e){text('connection','DISCONNECTED');text('error',e.message);}finally{setTimeout(poll,1000);}}
for(const button of document.querySelectorAll('[data-action]'))button.onclick=async()=>{try{state=await request('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:button.dataset.action})});update();}catch(e){text('error',e.message);}};
function update(){
 const r=state.report;generation=Math.floor(state.cursor/r.split);bar=state.cursor%r.split;const gen=r.generations[generation];flies=gen.flies;
 if(!flies.some(f=>f.id===selected))selected=flies[0].id;
 const modeLabel=r.mode==='historical_prices_assumed_liquidity'?'MARKET REPLAY':r.mode.toUpperCase();
 text('mode',modeLabel);text('phase',state.running?'TRAINING REPLAY RUNNING':'OBSERVER PAUSED');text('generation','GEN '+String(generation).padStart(2,'0'));
 text('bar','OBSERVATION '+(bar+1)+' / '+r.split);text('big-count',flies.length);text('diversity',gen.diversity+' UNIQUE GENOMES');
 const sourceLabel=typeof r.source==='object'?r.source.symbol+' · '+r.source.provider+' · execution liquidity assumed':(r.source||'seeded offline fixture');
 text('source-badge',modeLabel+' · '+sourceLabel);
 const c=state.collector;
 text('source-status',(c.fresh?'LIVE SNAPSHOTS':'SNAPSHOTS / '+c.status.toUpperCase())+' · '+c.verified_pairs+' PAIRS'+(c.observed_at?' · '+new Date(c.observed_at*1000).toISOString():''));
 $('tokens').replaceChildren();
 const observed=r.bars[bar];
 const input=element('div','','token');
 input.append(element('strong',typeof r.source==='object'?r.source.symbol+' / USD':'RUN INPUT / '+modeLabel),element('div','$'+number(observed.price,8),'price'),element('small',new Date(observed.timestamp*1000).toISOString()),element('small',r.methodology.historical_liquidity===false?'EXECUTION LIQUIDITY ASSUMPTION $'+number(observed.liquidity):'INPUT LIQUIDITY $'+number(observed.liquidity)));
 $('tokens').append(input,element('p','SEPARATE MARKET WATCH · snapshots below do not drive this archived run.'));
 for(const row of (c.rows||[]).slice(0,5)){
  const e=element('div','','token');e.append(element('strong',row.symbol+' / '+row.quote),element('div','$'+number(row.price,8),'price'),element('small','LIQUIDITY $'+number(row.liquidity)),element('small','CHAIN '+row.chain),element('small','TOKEN '+row.token_address),element('small','POOL '+row.pair_address));$('tokens').append(e);
 }
 if(!c.rows?.length)$('tokens').append(element('p','No verified market snapshots. Start the explicit collector; no fallback data is displayed.'));
 const key=generation+':'+selected;
 if(lastRender!==key){$('roster').replaceChildren();for(const fly of flies){const b=element('button',fly.id,fly.id===selected?'active':'');b.onclick=()=>{selected=fly.id;update();};$('roster').append(b);}lastRender=key;}
 inspect();
 $('events').replaceChildren();const visible=r.events.filter(e=>e.generation<=generation&&e.kind!=='holdout'&&e.kind!=='freeze'&&(e.kind==='birth'||e.generation<generation));
 for(const e of visible.slice(-18).reverse()){
  const line=element('div');line.append(element('strong','#'+e.sequence+' '+e.kind.toUpperCase()),document.createTextNode(' · '+(e.fly||e.best||'')+' · GEN '+e.generation+(e.parents?.length?' ← '+e.parents.join(', '):'')));$('events').append(line);
 }
 $('holdout').replaceChildren();
 if(state.cursor>=r.split*r.generations.length-1){for(const [name,result] of [['CHAMPION '+r.champion.id,r.holdout],...Object.entries(r.baselines)]){const row=element('div','','holdout-row');row.append(element('span',name.toUpperCase()),element('b',number(result.return*100)+'%'));$('holdout').append(row);}}
 else $('holdout').append(element('p','ARCHIVED RESULT — REVEALED AFTER PLAYBACK; AVAILABLE IN EXPORT'));
}
function inspect(){
 const f=flies.find(x=>x.id===selected);if(!f)return;const d=f.result.decisions[bar],curve=f.result.curve.slice(0,bar+1);
 text('fly-title',f.id);text('fly-meta','BORN GEN '+f.born+' · '+(curve.at(-1).holding?'HOLDING SIMULATED POSITION':'WATCHING / FLAT'));
 text('equity','$'+number(d.equity));let peak=1000,dd=0;for(const p of curve){peak=Math.max(peak,p.equity);dd=Math.max(dd,(peak-p.equity)/peak);}text('drawdown',number(dd*100)+'%');
 $('genome').replaceChildren();for(const [k,v] of Object.entries(f.genome))$('genome').append(element('dt',k.replaceAll('_',' ').toUpperCase()),element('dd',Number.isInteger(v)?v:number(v,4)));
 text('lineage',(f.parents.length?'PARENT '+f.parents.join(', '):'FOUNDER / RANDOM IMMIGRANT')+(f.mutations.length?'\n'+f.mutations.map(m=>m.gene+': '+number(m.before,5)+' → '+number(m.after,5)).join('\n'):' · no inherited mutations'));
 text('decision',d.action.toUpperCase()+' · '+d.reason+(d.pending?' → '+d.pending.toUpperCase()+' QUEUED FOR NEXT OBSERVATION':''));
 const c=$('curve'),x=c.getContext('2d');c.width=c.clientWidth*2;c.height=116;x.clearRect(0,0,c.width,c.height);const low=Math.min(995,...curve.map(p=>p.equity)),high=Math.max(1005,...curve.map(p=>p.equity));x.beginPath();curve.forEach((p,i)=>{const px=i/Math.max(1,state.report.split-1)*c.width,py=105-(p.equity-low)/(high-low)*94;i?x.lineTo(px,py):x.moveTo(px,py);});x.strokeStyle='#c2ff5a';x.lineWidth=2;x.stroke();
}
function draw(ts){
 const elapsed=Math.min(.05,(ts-lastFrame)/1000||0);lastFrame=ts;if(state?.running)visualTime+=elapsed;
 const rect=world.getBoundingClientRect(),w=rect.width,h=rect.height,dpr=window.devicePixelRatio||1;
 if(world.width!==Math.round(w*dpr)||world.height!==Math.round(h*dpr)){world.width=Math.round(w*dpr);world.height=Math.round(h*dpr);}
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
 ctx.strokeStyle='#202d2155';ctx.lineWidth=1;for(let x=20;x<w;x+=35){for(let y=20;y<h;y+=35){ctx.beginPath();ctx.moveTo(x-2,y);ctx.lineTo(x+2,y);ctx.moveTo(x,y-2);ctx.lineTo(x,y+2);ctx.stroke();}}
 // Habitat rings are spatial guides, not market data.
 ctx.strokeStyle='#44583733';for(const radius of [.21,.36]){ctx.beginPath();ctx.ellipse(w/2,h/2,w*radius,h*radius,0,0,Math.PI*2);ctx.stroke();}
 positions=flies.map(f=>({...Flight.position(f.id,visualTime,w,h),fly:f}));
 for(const p of positions){for(const parent of p.fly.parents){const q=positions.find(v=>v.fly.id===parent);if(q){ctx.strokeStyle='#c2ff5a22';ctx.setLineDash([3,6]);ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();ctx.setLineDash([]);}}}
 for(const p of positions){
  const f=p.fly,holding=f.result.curve[bar]?.holding,active=f.id===selected,color=holding?'#ff8953':'#c2ff5a';
  const next=Flight.position(f.id,visualTime+.01,w,h),angle=Math.atan2(next.y-p.y,next.x-p.x)+Math.PI/2;
  if(active){ctx.beginPath();ctx.arc(p.x,p.y,23,0,Math.PI*2);ctx.strokeStyle=color;ctx.lineWidth=1;ctx.stroke();ctx.fillStyle=color;ctx.font='10px monospace';ctx.textAlign='center';ctx.fillText(f.id,p.x,p.y+37);}
  ctx.save();ctx.translate(p.x,p.y);ctx.rotate(angle);const wing=.7+.3*Math.sin(visualTime*55+p.phase);
  ctx.strokeStyle='#748370';ctx.lineWidth=1;for(const side of [-1,1]){for(let k=0;k<3;k++){ctx.beginPath();ctx.moveTo(side*3,k*3-3);ctx.lineTo(side*(9+k),k*4-7);ctx.stroke();}}
  ctx.fillStyle='#d8edc966';for(const side of [-1,1]){ctx.save();ctx.rotate(side*.5*wing);ctx.beginPath();ctx.ellipse(side*7,-2,5,10,side*.4,0,Math.PI*2);ctx.fill();ctx.restore();}
  ctx.fillStyle='#34412c';ctx.strokeStyle=color;ctx.beginPath();ctx.ellipse(0,4,4,8,0,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle=color;ctx.beginPath();ctx.arc(0,-6,4,0,Math.PI*2);ctx.fill();ctx.fillStyle='#0b100d';for(const side of [-1,1]){ctx.beginPath();ctx.arc(side*2,-7,1.3,0,Math.PI*2);ctx.fill();}ctx.restore();
 }
 requestAnimationFrame(draw);
}
world.onclick=e=>{const rect=world.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;const hit=positions.map(p=>({p,d:Math.hypot(p.x-x,p.y-y)})).sort((a,b)=>a.d-b.d)[0];if(hit&&hit.d<35){selected=hit.p.fly.id;update();}};
window.flyHighProbe=()=>({flies:flies.length,selected,generation,bar,positions:positions.map(p=>({id:p.fly.id,x:p.x,y:p.y,phase:p.phase})),running:state?.running});
requestAnimationFrame(draw);poll();
