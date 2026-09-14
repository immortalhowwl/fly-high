'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function visitor(envelope,ok=true){
 const noop=()=>{},canvas=new Proxy({}, {get:()=>noop,set:()=>true});
 function element(){return {textContent:'',children:[],append(...nodes){this.children.push(...nodes);},replaceChildren(...nodes){this.children=nodes;},getContext:()=>canvas,getBoundingClientRect:()=>({width:600,height:400}),clientWidth:600};}
 const nodes={},buttons=['run','pause','reset','replay','generation'].map(action=>({...element(),dataset:{action}})),calls=[];
 const context=vm.createContext({console,URLSearchParams,AbortController,setTimeout,clearTimeout,requestAnimationFrame:noop,window:{location:{search:'?replay=wallet&wallet=wallet-a'},devicePixelRatio:1},document:{getElementById:id=>nodes[id]??=element(),createElement:element,createTextNode:element,querySelectorAll:()=>buttons},fetch:async(path)=>{calls.push(path);return {ok,status:ok?200:503,json:async()=>envelope};}});
 for(const file of ['motion.js','playback.js','app.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),context);
 return {context,nodes,calls,buttons,probe:()=>context.window.flyHighProbe()};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('optional replay fetch failure leaves research usable and cannot render hostile HTML',async()=>{
 class Node {constructor(){this.children=[];this.dataset={};this.value='';this.textContent='';} append(...n){this.children.push(...n);} replaceChildren(...n){this.children=n;} setAttribute(){} set innerHTML(v){throw Error('unsafe HTML');}}
 const nodes={},calls=[];
 const document={getElementById:id=>nodes[id]??=new Node(),createElement:()=>new Node(),querySelectorAll:()=>[],addEventListener(){}};
 const window={document,location:{hash:'#view=wallets&wallet=a'},addEventListener(){},fetch:async path=>{calls.push(path);if(path==='/api/wallet-replay')throw Error('offline');return {ok:true,json:async()=>({wallets:[{address:'a',handle:'<img onerror=alert(1)>'}],fills:[],tokens:[]})};}};
 vm.runInNewContext(fs.readFileSync('web/research.js','utf8'),{window,URL,URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval(){}});
 await settle();assert.deepEqual(calls,['/api/wallet-replay','/api/research','/api/behavior']);assert.equal(nodes['wallet-count'].textContent,'1');assert.match(nodes.status.textContent,/Snapshot loaded/);
 assert.ok(nodes.dossier.children.some(n=>n.textContent==='<img onerror=alert(1)>'));
});
test('research only links wallets with actual seeded founders, not mapping indices',()=>{
 const {walletReplayLink}=require('../web/research.js');
 assert.equal(walletReplayLink(null,'a'),null);
 assert.equal(walletReplayLink({status:'blocked',seed_count:0},'a'),null);
 const e={status:'completed',seed_count:1,mappings:[{provenance:{wallet:'rejected'}}],replay:{generations:[{flies:[{seed_origin:{provenance:{wallet:'a'}}}]}]}};
 assert.equal(walletReplayLink(e,'rejected'),null);
 assert.equal(walletReplayLink(e,'a'),'/?replay=wallet&wallet=a');
});
test('blocked wallet mode never loads archive and exposes reasons and correct exports',async()=>{
 const a=visitor({status:'blocked',seed_count:0,replay:null,blocked_reasons:['Cash evidence missing']});await settle();
 assert.deepEqual(a.calls,['/api/wallet-replay']);assert.equal(a.probe().flies,0);
 assert.match(a.nodes.error.textContent,/Cash evidence missing/);assert.equal(a.nodes['archive-link'].href,'/');
 assert.equal(a.nodes['export-run'].href,'/api/wallet-replay');assert.equal(a.nodes['export-ledger'].href,'/api/wallet-replay');
 assert.ok(a.buttons.every(b=>b.disabled));
});
test('unavailable wallet mode does not fall back',async()=>{
 const a=visitor({},false);await settle();assert.deepEqual(a.calls,['/api/wallet-replay']);assert.equal(a.probe().flies,0);assert.match(a.nodes.mode.textContent,/UNAVAILABLE/);
});
test('completed wallet mode uses supplied replay and shows founder and descendant provenance',async()=>{
 const report=JSON.parse(fs.readFileSync('examples/copy.report.json','utf8'));
 const founder=report.generations[0].flies[0];founder.seed_origin={provenance:{kind:'wallet_observations',wallet:'wallet-a',chain:'base',quote_asset:'WETH',observed_until:1,mapped_genes:{allocation:{sample_count:3}},unmapped_genes:{hold:'default'},uncertainties:['limited history']}};
 const birth=report.events.find(e=>e.kind==='birth'&&e.fly===founder.id);birth.seed_origin=founder.seed_origin;
 const a=visitor({status:'completed',seed_count:1,replay:report,limits:['Allocation only']});await settle();
 assert.deepEqual(a.calls,['/api/wallet-replay']);assert.equal(a.probe().flies,24);assert.match(a.nodes.mode.textContent,/WALLET-SEEDED/);
 assert.match(a.nodes.lineage.textContent,/wallet-a/);assert.match(a.nodes.lineage.textContent,/sample_count/);assert.match(a.nodes['source-status'].textContent,/SIMULATED/);
 const description=vm.runInContext('lineageText({id:"child",parents:["'+founder.id+'"],mutations:[]},state.report)',a.context);
 assert.match(description,/DERIVED DESCENDANT/);assert.match(description,/wallet-a/);assert.match(description,/not observed wallet/);
});
