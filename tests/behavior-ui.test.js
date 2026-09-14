'use strict';
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const ui = require('../web/research.js');
// Synthetic fixtures only; no production observations or performance claims.
function visitor(behavior, fail = false) {
  class Element {
    constructor(tag='div') { this.tagName=tag; this.children=[]; this.dataset={}; this.value=''; this._text=''; }
    set textContent(v) { this._text=String(v); this.children=[]; }
    get textContent() { return this._text+this.children.map(n=>n.textContent).join(''); }
    set innerHTML(v) { throw Error('unsafe HTML'); }
    append(...n) { this.children.push(...n); }
    replaceChildren(...n) { this._text=''; this.children=n; }
    setAttribute() {} focus() {}
  }
  const nodes={}, calls=[];
  const document={getElementById:id=>nodes[id] ||= new Element(),createElement:tag=>new Element(tag),querySelectorAll:()=>[],addEventListener(){}};
  const window={document,location:{hash:'#view=wallets&wallet=fixture-wallet'},addEventListener(){},fetch:async path=>{
    calls.push(path);
    if(path==='/api/behavior') { if(fail) throw Error('offline'); return {ok:true,json:async()=>behavior}; }
    return {ok:true,json:async()=>path==='/api/research'?{wallets:[{address:'fixture-wallet'}],fills:[],tokens:[]}:null};
  }};
  vm.runInNewContext(fs.readFileSync(require.resolve('../web/research.js'),'utf8'),{window,URL,URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval:()=>0});
  return {nodes,calls,settle:()=>new Promise(r=>setImmediate(r))};
}
const fixture=()=>({status:'hypotheses_available',integration_status:'awaiting_matching_market_window',default_genome:{min_liquidity:1000},wallets:[{wallet:'fixture-wallet',source:'<img onerror=evil()>',chain_id:4663,buy_count:3,sell_count:1,event_ids:[1,2,3,4],cadence:{median:12},order_size_usd:{median:20,sample_count:4,missing_or_invalid_count:0},attribution:{stale:true}}],candidates:[{id:'WH-fixture',execution:'not_run',genome:{min_liquidity:2000},provenance:{wallet:'fixture-wallet',token:'fixture-token',chain_id:4663,mapped_genes:{min_liquidity:{value:2000,event_ids:[1,2,3],formula:'fixture formula',clipped:false}},default_genes:{hold:12}}}]});
test('existing wallet dossier safely exposes observations and an unevaluated candidate',async()=>{
 const a=visitor(fixture());await a.settle();const content=a.nodes.dossier.textContent;
 assert.ok(a.calls.includes('/api/behavior'));assert.match(content,/Observed buys: 3/);assert.match(content,/12 seconds/);assert.match(content,/source-estimated/i);assert.match(content,/<img onerror=evil\(\)>/);
 assert.match(content,/WH-fixture/);assert.match(content,/min_liquidity: 1000 → 2000/);assert.match(content,/not_run/);assert.match(content,/awaiting_matching_market_window/);assert.match(content,/1, 2, 3/);
 assert.equal(ui.walletReplayLink(fixture(),'fixture-wallet'),null);
});
test('optional failure does not suppress research or strict replay messaging',async()=>{
 const a=visitor(null,true);await a.settle();assert.match(a.nodes.dossier.textContent,/Behavior evidence unavailable/);assert.match(a.nodes.dossier.textContent,/No admitted replay founder/);assert.match(a.nodes.status.textContent,/Snapshot loaded/);
});
test('invalid optional response stays unavailable and never renders an executable candidate',async()=>{
 const a=visitor({status:'completed',candidates:[{id:'evil'}]});await a.settle();assert.match(a.nodes.dossier.textContent,/Behavior evidence unavailable/);assert.doesNotMatch(a.nodes.dossier.textContent,/Open admitted wallet replay/);
});
