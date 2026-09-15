'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function visitor(envelope,ok=true,search='?replay=hypothesis&wallet=wallet-a'){
 const noop=()=>{},canvas=new Proxy({}, {get:()=>noop,set:()=>true});
 function element(tag){return {tag,textContent:'',children:[],append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;},getContext:()=>canvas,getBoundingClientRect:()=>({width:600,height:400}),clientWidth:600};}
 const nodes={},buttons=['run','pause','reset','replay','generation'].map(action=>({...element(),dataset:{action}})),calls=[];
 const labels={'.holdout .panel-title':[element()],'.holdout p':[element()],'.market dt':[element()]};labels['.market dt'][0].textContent='Train / holdout';
 const context=vm.createContext({console,URLSearchParams,AbortController,setTimeout,clearTimeout,requestAnimationFrame:noop,window:{location:{search},devicePixelRatio:1},document:{getElementById:id=>nodes[id]??=element(),createElement:element,createTextNode:element,querySelectorAll:q=>q==='[data-action]'?buttons:labels[q]||[]},fetch:async(path)=>{calls.push(path);return {ok,status:ok?200:503,json:async()=>envelope};}});
 for(const file of ['motion.js','playback.js','app.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),context);
 context.Flight=context.window.Flight; // Browser window properties are globals; VM window is a separate test object.
 return {context,nodes,calls,buttons,labels,probe:()=>context.window.flyHighProbe()};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('home defaults to hypothesis, flies move without advancing results, Watch evolution is local and restarts at end',async()=>{
 const a=visitor(completed(),true,''),b=visitor(completed(),true,'');await settle();
 assert.deepEqual(a.calls,['/api/hypothesis-replay']);assert.ok(a.probe().flies>0);assert.equal(a.probe().running,false);
 vm.runInContext('draw(100);draw(150)',a.context);const before=a.probe();vm.runInContext('draw(200)',a.context);
 assert.notEqual(a.probe().positions[0].x,before.positions[0].x);assert.equal(a.probe().bar,0);
 const run=a.buttons.find(x=>x.dataset.action==='run');await run.onclick();assert.equal(a.probe().running,true);assert.equal(b.probe().running,false);
 vm.runInContext('playback.cursor=playback.end;playback.running=false;syncPlayback();update()',a.context);
 assert.ok(a.nodes.holdout.children.length);await run.onclick();assert.equal(a.probe().bar,0);assert.equal(a.probe().generation,0);assert.equal(a.probe().running,true);
 assert.deepEqual(a.calls,['/api/hypothesis-replay']);
});
test('simple English hierarchy keeps secondary controls and evidence closed, risk visible',()=>{
 const html=fs.readFileSync('web/index.html','utf8'),research=fs.readFileSync('web/research.html','utf8');
 assert.match(html,/<button data-action="run">Watch evolution<\/button>/);
 assert.equal((html.match(/data-action="run"/g)||[]).length,1);
 assert.match(html,/<details class="playback-controls"><summary>Playback controls<\/summary>/);
 for(const action of ['pause','generation','replay','reset'])assert.match(html,new RegExp('<details class="playback-controls">[\\s\\S]*data-action="'+action+'"[\\s\\S]*<\\/details>'));
 assert.match(html,/CLICK A FLY TO SEE ITS STORY/);assert.match(html,/<details><summary>Details · genome and raw evidence/);
 for(const label of ['Origin','Changes','Trades · simulated','Results · simulated'])assert.ok(html.includes(label));
 assert.match(html,/<p class="risk-note">Exits assumed · honeypot risk remains/);
 assert.doesNotMatch(html,/<details[^>]*\bopen\b/);
 assert.match(research,/Third-party data · partial history/);assert.match(research,/<details><summary>Details · source, freshness and warnings/);
 assert.match(research,/<\/details>\s*<div id="status"/);
});
function completed(){const report=JSON.parse(fs.readFileSync('examples/copy.report.json','utf8'));const founder=report.generations[0].flies[0];founder.seed_origin={provenance:{kind:'wallet_inspired_hypothesis',wallet:'wallet-a',mapped_genes:{min_liquidity:{value:5000,event_ids:['real-source-event']}},default_genes:{hold:8}}};report.events.find(e=>e.kind==='birth'&&e.fly===founder.id).seed_origin=founder.seed_origin;return {status:'completed',evaluation_kind:'retrospective',seed_count:1,replay:report,limits:['Not forward validation'],overlap_note:'Wallet evidence overlaps final segment'};}
test('founder-gated link, never candidate-index admission',()=>{const {hypothesisReplayLink}=require('../web/research.js');const e=completed();e.candidates=[{provenance:{wallet:'rejected'}}];assert.equal(hypothesisReplayLink(e,'wallet-a'),'/?replay=hypothesis&wallet=wallet-a');assert.equal(hypothesisReplayLink(e,'rejected'),null);assert.equal(hypothesisReplayLink({...e,status:'blocked'},'wallet-a'),null);assert.equal(hypothesisReplayLink({...e,evaluation_kind:'forward'},'wallet-a'),null);});
test('blocked, unavailable and malformed replay never load archive',async()=>{for(const [e,ok] of [[{status:'blocked',seed_count:0,replay:null,blocked_reasons:['Missing matching market']},true],[{},false],[{status:'completed',seed_count:1,replay:{}},true]]){const a=visitor(e,ok);await settle();assert.deepEqual(a.calls,['/api/hypothesis-replay']);assert.equal(a.probe().flies,0);assert.ok(a.buttons.every(b=>b.disabled));assert.equal(a.nodes['export-run'].href,'/api/hypothesis-replay');assert.equal(a.nodes['export-ledger'].href,'/api/hypothesis-replay');assert.equal(a.nodes['archive-link'].href,'/?replay=archive');assert.match(a.nodes.mode.textContent,/BLOCKED|UNAVAILABLE/);}});
test('completed uses correct report, provenance, overlap, source, trades and parent navigation',async()=>{const e=completed(),a=visitor(e);await settle();assert.deepEqual(a.calls,['/api/hypothesis-replay']);assert.equal(a.probe().flies,e.replay.generations[0].flies.length);assert.equal(a.nodes.mode.textContent,'RETROSPECTIVE WALLET-INSPIRED SIMULATION');assert.match(a.nodes['replay-details'].textContent,/Wallet evidence overlaps final segment/);assert.match(a.nodes['raw-evidence'].textContent,/real-source-event/);assert.match(a.nodes['mode'].textContent,/RETROSPECTIVE/);assert.match(a.labels['.holdout .panel-title'][0].textContent,/RETROSPECTIVE SIMULATION/);assert.equal(a.labels['.market dt'][0].textContent,'Replay segments');assert.ok(a.nodes.trades.children.length);const child=e.replay.generations[1].flies.find(f=>f.parents?.length);assert.ok(child);vm.runInContext('state.cursor=state.report.split;selected='+JSON.stringify(child.id)+';update()',a.context);const parent=a.nodes.lineage.children.find(n=>n.tag==='button'&&n.textContent.startsWith('INSPECT PARENT'));assert.ok(parent);parent.onclick();assert.equal(a.probe().selected,child.parents[0]);});
test('optional hypothesis failure cannot block research data',async()=>{class Node{constructor(){this.children=[];this.dataset={};this.value='';this.textContent='';}append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;}setAttribute(){}set innerHTML(v){throw Error('unsafe HTML');}}const nodes={},calls=[];const document={getElementById:id=>nodes[id]??=new Node(),createElement:()=>new Node(),querySelectorAll:()=>[],addEventListener(){}};const window={document,location:{hash:'#view=wallets&wallet=a'},addEventListener(){},fetch:async path=>{calls.push(path);if(path.includes('replay'))throw Error('offline');return {ok:true,json:async()=>({wallets:[{address:'a',handle:'wallet'}],fills:[],tokens:[]})};}};vm.runInNewContext(fs.readFileSync('web/research.js','utf8'),{window,URL,URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval(){}});await settle();assert.ok(calls.includes('/api/hypothesis-replay'));assert.equal(nodes['wallet-count'].textContent,'1');assert.match(nodes.status.textContent,/Snapshot loaded/);});
