'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function visitor(data,ok=true){
 class E{constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.value='';this.hidden=false;this.attributes={};this._text='';}set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(c=>c.textContent).join(' ');}set innerHTML(v){throw Error('Unsafe HTML');}append(...n){this.children.push(...n);}replaceChildren(...n){this._text='';this.children=[...n];}setAttribute(k,v){this.attributes[k]=v;}focus(){}}
 const nodes={'obs-feed':new E()},document={getElementById:id=>nodes[id] ||=new E(),createElement:t=>new E(t)},calls=[];
 const window={document,location:{search:''},fetch:async p=>{calls.push(p);return {ok,json:async()=>data};}};
 const c=vm.createContext({window,URLSearchParams,AbortController,setTimeout,clearTimeout,console});
 assert.ok(fs.existsSync('web/observation.js'),'Observation interface is not implemented');
 vm.runInContext(fs.readFileSync('web/observation.js','utf8'),c);
 return {nodes,calls,settle:()=>new Promise(r=>setImmediate(r))};
}
const A='0x'+'a'.repeat(40),B='0x'+'b'.repeat(40),T='0x'+'c'.repeat(40);
function fixture(){const ev=(id,wallet,side)=>({id,wallet,handle:wallet===A?'Alpha':'Beta',side,token:T,symbol:'<b>TOKEN</b>',ts:150,usd:12,transaction_url:'https://robinhoodchain.blockscout.com/tx/0x'+'1'.repeat(64),flags:[]});return {roster:[{address:A,handle:'Alpha',events:2},{address:B,handle:'Beta',events:1}],events:[ev('1',A,'buy'),ev('2',B,'buy'),ev('3',A,'sell')],groups:[{token:T,symbol:'<b>TOKEN</b>',wallets:[A,B],event_ids:['1','2'],last_ts:150}],exits:[ev('3',A,'sell')],counts:{roster:2,source_rows:3,events:3,excluded_or_duplicate:0,buys:2,sells:1,groups:1},rules:{trader:'Selected wallet buys and sells',group:'At least 2 distinct wallets',exits:'Sales; not necessarily a full exit'},source:{name:'Fixture source',captured_at:'2026-09-15T00:00:00Z',stale:false},window:{since:100,until:200},limits:'Not independently verified'};}
test('three flies select real rule events, readable evidence and distinct group wallets',async()=>{
 const v=visitor(fixture());await v.settle();
 assert.deepEqual(v.calls,['/api/observations']);
 assert.equal(v.nodes['obs-feed'].children.length,2);
 v.nodes['obs-feed'].children[0].onclick();assert.match(v.nodes['obs-detail'].textContent,/Alpha/);assert.match(v.nodes['obs-detail'].textContent,/Source-estimated/);
 v.nodes['fly-group'].onclick();assert.match(v.nodes['obs-rule'].textContent,/2 distinct/);assert.equal(v.nodes['obs-feed'].children.length,1);
 v.nodes['obs-feed'].children[0].onclick();assert.match(v.nodes['obs-detail'].textContent,/Alpha/);assert.match(v.nodes['obs-detail'].textContent,/Beta/);assert.match(v.nodes['obs-detail'].textContent,/<b>TOKEN<\/b>/);
 v.nodes['fly-exits'].onclick();assert.equal(v.nodes['obs-feed'].children.length,1);assert.match(v.nodes['obs-feed'].textContent,/SELL/);
 v.nodes['fly-trader'].onclick();v.nodes['obs-wallet'].value=B;v.nodes['obs-wallet'].onchange();assert.equal(v.nodes['obs-feed'].children.length,1);assert.match(v.nodes['obs-feed'].textContent,/Beta/);
});
test('empty and failure states never substitute simulation or fabricated signals',async()=>{
 const f=fixture();f.events=[];f.groups=[];f.exits=[];
 const v=visitor(f);await v.settle();assert.match(v.nodes['obs-feed'].textContent,/No qualifying/);
 v.nodes['fly-group'].onclick();assert.match(v.nodes['obs-feed'].textContent,/No qualifying/);
 const bad=visitor(f,false);await bad.settle();assert.match(bad.nodes['obs-status'].textContent,/unavailable/i);assert.equal(bad.nodes['obs-feed'].children.length,0);
});
