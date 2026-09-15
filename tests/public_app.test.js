'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const report=JSON.parse(fs.readFileSync('examples/copy.report.json','utf8'));
function visitor(){
 const noop=()=>{},canvas=new Proxy({}, {get:()=>noop,set:()=>true});
 function element(){return {textContent:'',append:noop,replaceChildren:noop,getContext:()=>canvas,getBoundingClientRect:()=>({width:600,height:400}),clientWidth:600};}
 const nodes={},buttons=['run','pause','reset','replay','generation'].map(action=>({...element(),dataset:{action}})),calls=[];
 const context=vm.createContext({console,URLSearchParams,AbortController,setTimeout,clearTimeout,requestAnimationFrame:noop,window:{location:{search:'?replay=archive'},devicePixelRatio:1},document:{getElementById:id=>nodes[id]??=(element()),createElement:element,createTextNode:element,querySelectorAll:()=>buttons},fetch:async(path)=>{calls.push(path);return {ok:true,json:async()=>({public:true,running:false,cursor:0,report,collector:{status:'disabled_public_replay',fresh:false,rows:[],verified_pairs:0}})};}});
 for(const file of ['motion.js','playback.js','app.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),context);
 return {context,nodes,calls,click:action=>buttons.find(b=>b.dataset.action===action).onclick(),probe:()=>context.window.flyHighProbe()};
}
test('public app loads once, uses no control API, isolates tabs and renders archive labels',async()=>{
 const a=visitor(),b=visitor();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(a.probe().flies,24);
 await a.click('run');assert.equal(a.probe().running,true);assert.equal(b.probe().running,false);
 await a.click('generation');assert.equal(a.probe().generation,1);assert.equal(b.probe().generation,0);
 await a.click('reset');assert.equal(a.probe().generation,0);assert.equal(a.probe().running,false);
 assert.deepEqual(a.calls,['/api/state']);assert.deepEqual(b.calls,['/api/state']);
 assert.equal(a.nodes['source-status'].textContent,'Historical archive · not live');
 assert.match(a.nodes.connection.textContent,/LOCAL PLAYBACK/);
 assert.equal(a.nodes.error.textContent,'');
});
