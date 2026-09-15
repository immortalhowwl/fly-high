'use strict';
const $=id=>document.getElementById(id),world=$('world'),ctx=world.getContext('2d');
let state=null,selected=null,flies=[],generation=0,bar=0,positions=[],visualTime=0,lastFrame=0,lastRender='';
let playback=null;
const replayMode=new URLSearchParams(window.location?.search||'').get('replay')||'hypothesis';
const hypothesisMode=replayMode==='hypothesis',walletMode=replayMode==='wallet',seededMode=walletMode||hypothesisMode;
const replayEndpoint=hypothesisMode?'/api/hypothesis-replay':'/api/wallet-replay';
const replayLabel=hypothesisMode?'RETROSPECTIVE WALLET-INSPIRED SIMULATION':'WALLET-SEEDED';
function overlapText(e){const note=e?.overlap_note||e?.overlap||e?.temporal_overlap;return note?(typeof note==='string'?note:JSON.stringify(note)):'';}
function retrospectiveLabels(){if(!hypothesisMode)return;for(const node of document.querySelectorAll('.holdout .panel-title'))node.textContent='FINAL RESULTS · RETROSPECTIVE SIMULATION';for(const node of document.querySelectorAll('.holdout p:not(.risk-note)'))node.textContent='Historical experiment, not forward validation. Wallet evidence may overlap these prices.';for(const node of document.querySelectorAll('.market dt'))if(/holdout/i.test(node.textContent))node.textContent='Replay segments';}
let walletEnvelope=null;
function lineageText(f,r){
 const provenance=f.seed_origin?.provenance;
 const births=new Map((r.events||[]).filter(e=>e.kind==='birth').map(e=>[e.fly,e]));
 const seen=new Set(),origins=new Set();
 function visit(id){if(seen.has(id))return;seen.add(id);const node=births.get(id);if(node?.seed_origin?.provenance?.wallet)origins.add(node.seed_origin.provenance.wallet);for(const p of node?.parents||[])visit(p);}
 for(const p of f.parents||[])visit(p);
 const origin=provenance?(hypothesisMode?'WALLET-INSPIRED HYPOTHESIS FOUNDER · not recovered strategy\n':'WALLET-SEEDED FOUNDER · partial mapping, not recovered strategy\n')+(provenance.wallet||'supplied parameters'):origins.size?'DERIVED DESCENDANT · '+[...origins].join(', ')+' · simulated inheritance, not observed wallet behaviour':(f.parents?.length?'PARENT '+f.parents.join(', '):'FOUNDER / RANDOM IMMIGRANT');
 return origin;
}
function walletStatus(message,blocked=false){
 text('replay-status',message);$('archive-link').hidden=false;$('archive-link').href='/?replay=archive';
 for(const id of ['export-run','export-ledger']){$(id).href=replayEndpoint;$(id).textContent=id==='export-run'?'EXPORT '+(hypothesisMode?'HYPOTHESIS':'SEEDED')+' ENVELOPE ↗':(hypothesisMode?'HYPOTHESIS':'SEEDED')+' ENVELOPE / EVENTS ↗';}
 for(const button of document.querySelectorAll('[data-action]'))button.disabled=blocked;
}
async function pollWallet(){
 retrospectiveLabels();walletStatus('Loading precomputed '+replayLabel+'…',true);text('big-count','0');
 try{
  walletEnvelope=await request(replayEndpoint);
  const e=walletEnvelope,r=e.replay;
  if(e.status!=='completed'||(hypothesisMode&&e.evaluation_kind!=='retrospective')||!Number.isInteger(e.seed_count)||e.seed_count<1||!r?.generations?.length||!r.split){
   const reason=(e.blocked_reasons||[]).join('\n')||'No admitted wallet seeds in a completed replay.';
   state=null;playback=null;flies=[];text('mode',replayLabel+(e.status==='blocked'?' / BLOCKED':' / UNAVAILABLE'));text('connection','NO SEEDED REPLAY');text('source-status','NOT RUN · no archive substituted');text('phase','NO SIMULATION RUN');text('error',reason);walletStatus(reason,true);return;
  }
  state={public:true,running:false,cursor:0,report:r,collector:{rows:[],fresh:false,status:'disabled_wallet_replay'}};
  const wanted=new URLSearchParams(window.location.search).get('wallet');
  selected=r.generations[0].flies.find(f=>f.seed_origin?.provenance?.wallet===wanted)?.id||null;
  playback=new Playback(r);update();text('connection','● '+replayLabel+' · LOCAL PLAYBACK');text('error','');
  walletStatus((wanted&&!r.generations[0].flies.some(f=>f.seed_origin?.provenance?.wallet===wanted)?'Requested wallet is not admitted; showing the separate admitted population. ':'')+e.seed_count+(hypothesisMode?' wallet-inspired founders':' admitted founders')+'. Click a fly to see its story.');
  text('replay-details','Simulation, not wallet execution or recovered strategy. '+overlapText(e)+' '+(e.limits||[]).join(' '));
 }catch(e){state=null;playback=null;flies=[];text('mode',replayLabel+' / UNAVAILABLE');text('connection','NO SEEDED REPLAY');text('source-status','UNAVAILABLE · no archive substituted');text('phase','NO SIMULATION RUN');text('error',e.message);walletStatus('Precomputed wallet replay unavailable. '+e.message,true);}
}
const number=(n,d=2)=>Number(n).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const text=(id,value)=>$(id).textContent=value;
function element(tag,content,cls){const e=document.createElement(tag);e.textContent=content;if(cls)e.className=cls;return e;}
async function request(path,options){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);try{const response=await fetch(path,{...options,signal:controller.signal});if(!response.ok)throw Error('HTTP '+response.status);return await response.json();}finally{clearTimeout(timer);}}
function syncPlayback(){state.cursor=Math.floor(playback.cursor);state.running=playback.running;}
async function poll(){try{const next=await request('/api/state'+(state?'?brief=1':''));state={...state,...next};if(state.public&&!playback)playback=new Playback(state.report);update();text('connection',state.public?'● HISTORICAL ARCHIVE · LOCAL PLAYBACK':'● LOCAL ENGINE CONNECTED');text('error','');}catch(e){text('connection','DISCONNECTED');text('error',e.message);}finally{if(!state?.public)setTimeout(poll,1000);}}
for(const button of document.querySelectorAll('[data-action]'))button.onclick=async()=>{try{if(!state)return;if(playback){playback.control(button.dataset.action==='run'&&playback.cursor>=playback.end?'replay':button.dataset.action);syncPlayback();}else state=await request('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:button.dataset.action})});update();}catch(e){text('error',e.message);}};
function update(){
 const r=state.report;generation=Math.floor(state.cursor/r.split);bar=state.cursor%r.split;const gen=r.generations[generation];flies=gen.flies;
 if(!flies.some(f=>f.id===selected))selected=flies[0].id;
 const modeLabel=seededMode?replayLabel:r.mode==='historical_prices_assumed_liquidity'?'MARKET REPLAY':r.mode.toUpperCase();
 text('mode',modeLabel);text('phase',state.running?'ARCHIVED TRAINING REPLAY RUNNING':'ARCHIVED REPLAY PAUSED');text('generation','GEN '+String(generation).padStart(2,'0'));
 text('bar','OBSERVATION '+(bar+1)+' / '+r.split);text('big-count',flies.length);text('diversity',gen.diversity+' UNIQUE GENOMES');
 const sourceLabel=typeof r.source==='object'?r.source.symbol+' · '+r.source.provider+' · execution liquidity assumed':(r.source||'seeded offline fixture');

 const c=state.collector;
 text('source-status',seededMode?'Historical prices · assumed liquidity':state.public?'Historical archive · not live':(c.fresh?'LIVE SNAPSHOTS':'SNAPSHOTS / '+c.status.toUpperCase())+' · '+c.verified_pairs+' PAIRS'+(c.observed_at?' · '+new Date(c.observed_at*1000).toISOString():''));
 $('tokens').replaceChildren();
 const observed=r.bars[bar];
 const input=element('div','','token');
 input.append(element('strong',typeof r.source==='object'?r.source.symbol+' / USD':'RUN INPUT / '+modeLabel),element('div','$'+number(observed.price,8),'price'),element('small',new Date(observed.timestamp*1000).toISOString()),element('small',r.methodology.historical_liquidity===false?'EXECUTION LIQUIDITY ASSUMPTION $'+number(observed.liquidity):'INPUT LIQUIDITY $'+number(observed.liquidity)));
 $('tokens').append(input);
 if(c.rows?.length)$('tokens').append(element('p','Separate market snapshots · not replay inputs.'));
 for(const row of (c.rows||[]).slice(0,5)){
  const e=element('div','','token');e.append(element('strong',row.symbol+' / '+row.quote),element('div','$'+number(row.price,8),'price'),element('small','LIQUIDITY $'+number(row.liquidity)),element('small','CHAIN '+row.chain),element('small','TOKEN '+row.token_address),element('small','POOL '+row.pair_address));$('tokens').append(e);
 }
 if(!c.rows?.length&&!state.public)$('tokens').append(element('p','No verified market snapshots. No fallback data is displayed.'));
 const key=generation+':'+selected;
 if(lastRender!==key){$('roster').replaceChildren();for(const fly of flies){const b=element('button',fly.id,fly.id===selected?'active':'');b.onclick=()=>{selected=fly.id;update();};$('roster').append(b);}lastRender=key;}
 inspect();
 $('events').replaceChildren();const visible=r.events.filter(e=>e.generation<=generation&&e.kind!=='holdout'&&e.kind!=='freeze'&&(e.kind==='birth'||e.generation<generation));
 for(const e of visible.slice(-18).reverse()){
  const line=element('div');line.append(element('strong','#'+e.sequence+' '+e.kind.toUpperCase()),document.createTextNode(' · '+(e.fly||e.best||'')+' · GEN '+e.generation+(e.parents?.length?' ← '+e.parents.join(', '):'')+(e.seed_origin?' · SEEDED FOUNDER '+(e.seed_origin.provenance?.wallet||'supplied genome'):'')));$('events').append(line);
 }
 $('holdout').replaceChildren();
 if(state.cursor>=r.split*r.generations.length-1){for(const [name,result] of [['CHAMPION '+r.champion.id,r.holdout],...Object.entries(r.baselines)]){const row=element('div','','holdout-row');row.append(element('span',name.toUpperCase()),element('b',number(result.return*100)+'%'));$('holdout').append(row);}}
 else $('holdout').append(element('p','ARCHIVED RESULT — REVEALED AFTER PLAYBACK; AVAILABLE IN EXPORT'));
}
// Display labels follow engine.py's existing seven genes; exact values remain in Details.
function mutationText(m){
 const labels={lookback:['Price lookback','Observations used to measure the price change.'],momentum:['Entry threshold','Minimum price change needed to queue a buy.'],min_liquidity:['Minimum liquidity','Liquidity required before a buy can fill.'],stop:['Stop-loss threshold','Price drop from entry that queues a sell.'],take:['Take-profit threshold','Price rise from entry that queues a sell.'],hold:['Holding limit','Observations after entry before a sell is queued.'],allocation:['Cash allocation','Share of available cash budgeted for a buy, before fees and liquidity caps.']};
 const [label,explanation]=labels[m.gene]||[m.gene.replaceAll('_',' '),'Changed strategy parameter.'];
 const value=v=>['momentum','stop','take','allocation'].includes(m.gene)?number(v*100)+'%':m.gene==='min_liquidity'?'$'+number(v):['lookback','hold'].includes(m.gene)?number(v,0)+' observations':number(v,5);
 return label+': '+value(m.before)+' → '+value(m.after)+'\n'+explanation;
}
function inspect(){
 const f=flies.find(x=>x.id===selected);if(!f)return;const d=f.result.decisions[bar],curve=f.result.curve.slice(0,bar+1);
 text('fly-title',f.id);text('fly-meta','BORN GEN '+f.born+' · '+(curve.at(-1).holding?'HOLDING SIMULATED POSITION':'WATCHING / FLAT'));
 text('equity','$'+number(d.equity));let peak=1000,dd=0;for(const p of curve){peak=Math.max(peak,p.equity);dd=Math.max(dd,(peak-p.equity)/peak);}text('drawdown',number(dd*100)+'%');
 $('genome').replaceChildren();for(const [k,v] of Object.entries(f.genome)){const description=mutationText({gene:k,before:v,after:v});const label=description.split(': ')[0],value=description.split(': ')[1].split(' → ')[0];$('genome').append(element('dt',label),element('dd',value));}
 text('lineage',lineageText(f,state.report));
 for(const parent of f.parents||[]){
  const target=state.report.generations.findIndex(g=>g.flies.some(x=>x.id===parent));
  if(target>=0){const button=element('button','INSPECT PARENT '+parent);button.onclick=()=>{playback?.control('pause');if(playback)playback.cursor=target*state.report.split;state.cursor=target*state.report.split;state.running=false;selected=parent;update();};$('lineage').append(button);}
 }
 text('changes',f.mutations?.length?f.mutations.map(mutationText).join('\n\n'):(f.parents?.length?'No recorded mutations. Parameters inherited from parents.':'Starting parameters · no mutations yet.'));
 const visibleTrades=(f.result.trades||[]).filter(t=>t.timestamp<=d.timestamp);
 $('trades').replaceChildren();
 for(const trade of visibleTrades.slice(-5))$('trades').append(element('p',(trade.side||trade.action||'fill').toUpperCase()+' · '+(trade.price!=null?'$'+number(trade.price,8)+' · ':'')+new Date(trade.timestamp*1000).toISOString()));
 if(!visibleTrades.length)$('trades').append(element('p','No simulated trades yet.'));
 else $('trades').append(element('small',visibleTrades.length+' simulated fills so far. Latest five shown; full list in Details.'));
 $('raw-evidence').replaceChildren(element('h4','All simulated trades so far'));
 if(!visibleTrades.length)$('raw-evidence').append(element('p','No simulated trades yet.'));
 for(const trade of visibleTrades){
  const row=element('p',(trade.side||trade.action||'fill').toUpperCase()+' · '+new Date(trade.timestamp*1000).toLocaleString('en-GB',{timeZone:'UTC'})+' UTC');
  row.append(element('br'),element('span','Price: $'+number(trade.price,8)+(trade.quantity!=null?' · Quantity: '+number(trade.quantity,4):'')+(trade.fee!=null?' · Fee: $'+number(trade.fee):'')));
  $('raw-evidence').append(row);
 }
 const cancelled=f.result.decisions.slice(0,bar+1).filter(x=>x.action==='cancel');
 if(cancelled.length){$('raw-evidence').append(element('h4','Orders that did not execute'));for(const order of cancelled)$('raw-evidence').append(element('p',new Date(order.timestamp*1000).toLocaleString('en-GB',{timeZone:'UTC'})+' UTC · '+order.reason));}
 if(bar===state.report.split-1)$('raw-evidence').append(element('h4','Generation result · simulated'),element('p','Return: '+number(f.result.return*100)+'% · Maximum drawdown: '+number(f.result.drawdown*100)+'% · Fees: $'+number(f.result.fees)),element('p',f.result.mark_note||''));
 text('decision',d.action.toUpperCase()+' · '+d.reason+(d.pending?' → '+d.pending.toUpperCase()+' QUEUED FOR NEXT OBSERVATION':''));
 const c=$('curve'),x=c.getContext('2d');c.width=c.clientWidth*2;c.height=116;x.clearRect(0,0,c.width,c.height);const low=Math.min(995,...curve.map(p=>p.equity)),high=Math.max(1005,...curve.map(p=>p.equity));x.beginPath();curve.forEach((p,i)=>{const px=i/Math.max(1,state.report.split-1)*c.width,py=105-(p.equity-low)/(high-low)*94;i?x.lineTo(px,py):x.moveTo(px,py);});x.strokeStyle='#00ff85';x.lineWidth=2;x.stroke();
}
function draw(ts){
 const elapsed=Math.min(.05,(ts-lastFrame)/1000||0);lastFrame=ts;if(state)visualTime+=elapsed;
 if(playback?.running){const previous=state.cursor;playback.tick(elapsed);syncPlayback();if(previous!==state.cursor||!state.running)update();}
 const rect=world.getBoundingClientRect(),w=rect.width,h=rect.height,dpr=window.devicePixelRatio||1;
 if(world.width!==Math.round(w*dpr)||world.height!==Math.round(h*dpr)){world.width=Math.round(w*dpr);world.height=Math.round(h*dpr);}
 ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
 ctx.strokeStyle='#60606033';ctx.lineWidth=1;for(let x=20;x<w;x+=35){for(let y=20;y<h;y+=35){ctx.beginPath();ctx.moveTo(x-2,y);ctx.lineTo(x+2,y);ctx.moveTo(x,y-2);ctx.lineTo(x,y+2);ctx.stroke();}}
 // Habitat rings are spatial guides, not market data.
 ctx.strokeStyle='#60606033';for(const radius of [.21,.36]){ctx.beginPath();ctx.ellipse(w/2,h/2,w*radius,h*radius,0,0,Math.PI*2);ctx.stroke();}
 positions=flies.map(f=>({...Flight.position(f.id,visualTime,w,h),fly:f}));
 for(const p of positions){for(const parent of p.fly.parents){const q=positions.find(v=>v.fly.id===parent);if(q){ctx.strokeStyle='#00ff8522';ctx.setLineDash([3,6]);ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();ctx.setLineDash([]);}}}
 for(const p of positions){
  const f=p.fly,holding=f.result.curve[bar]?.holding,active=f.id===selected,color=holding?'#ff8a00':'#00ff85';
  const next=Flight.position(f.id,visualTime+.01,w,h),angle=Math.atan2(next.y-p.y,next.x-p.x)+Math.PI/2;
  if(active){ctx.beginPath();ctx.arc(p.x,p.y,23,0,Math.PI*2);ctx.strokeStyle=color;ctx.lineWidth=1;ctx.stroke();ctx.fillStyle=color;ctx.font='10px monospace';ctx.textAlign='center';ctx.fillText(f.id,p.x,p.y+37);}
  ctx.save();ctx.translate(p.x,p.y);ctx.rotate(angle);const wing=.7+.3*Math.sin(visualTime*55+p.phase);
  ctx.strokeStyle='#949494';ctx.lineWidth=1;for(const side of [-1,1]){for(let k=0;k<3;k++){ctx.beginPath();ctx.moveTo(side*3,k*3-3);ctx.lineTo(side*(9+k),k*4-7);ctx.stroke();}}
  ctx.fillStyle='#ffffff66';for(const side of [-1,1]){ctx.save();ctx.rotate(side*.5*wing);ctx.beginPath();ctx.ellipse(side*7,-2,5,10,side*.4,0,Math.PI*2);ctx.fill();ctx.restore();}
  ctx.fillStyle='#101010';ctx.strokeStyle=color;ctx.beginPath();ctx.ellipse(0,4,4,8,0,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle=color;ctx.beginPath();ctx.arc(0,-6,4,0,Math.PI*2);ctx.fill();ctx.fillStyle='#000000';for(const side of [-1,1]){ctx.beginPath();ctx.arc(side*2,-7,1.3,0,Math.PI*2);ctx.fill();}ctx.restore();
 }
 requestAnimationFrame(draw);
}
world.onclick=e=>{const rect=world.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;const hit=positions.map(p=>({p,d:Math.hypot(p.x-x,p.y-y)})).sort((a,b)=>a.d-b.d)[0];if(hit&&hit.d<35){selected=hit.p.fly.id;update();}};
window.flyHighProbe=()=>({flies:flies.length,selected,generation,bar,positions:positions.map(p=>({id:p.fly.id,x:p.x,y:p.y,phase:p.phase})),running:state?.running});
requestAnimationFrame(draw);if(seededMode)pollWallet();else poll();
