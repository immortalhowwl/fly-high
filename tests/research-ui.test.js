'use strict';
// Explicit test fixtures only. Production UI never imports or generates these rows.
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const ui = require('../web/research.js');
const fixture = () => ({as_of: '2026-09-14T19:00:00Z', source: 'TEST FIXTURE INDEXER', window: '7d', coverage: {limited: true}, wallets: [{address: 'test-wallet', handle: '<img src=x onerror=alert(1)>', realized_pnl: -10, unrealized_pnl: 20, net_pnl: 10, fills: 999, win_rate: 0.25}], fills: [{id: 'fixture-fill', ts: 1789412400, tx: 'test-tx', wallet: 'test-wallet', token: 'test-token', side: 'sell', usd: 10, amount: 2, symbol: 'FIXTURE'}], tokens: [{token: 'test-token', symbol: 'FIXTURE', liquidity: 8.48, drained: true, usd_in: 100, usd_out: 10}], metrics: {global_total: 99999}, warnings: ['TEST FIXTURE — not production data']});
function visitor(responseData = fixture(), ok = true) {
  class Element {
    constructor(tag='div') { this.tagName=tag; this.children=[]; this.attributes={}; this.dataset={}; this.value=''; this.hidden=false; this._text=''; }
    set textContent(value) { this._text=String(value); this.children=[]; }
    get textContent() { return this._text + this.children.map(n=>n.textContent).join(''); }
    set innerHTML(_) { throw new Error('Unsafe HTML rendering attempted'); }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this._text=''; this.children=[...nodes]; }
    setAttribute(key,value) { this.attributes[key]=String(value); }
    focus() { this.focused=true; }
    click() { if(this.onclick) this.onclick(); }
  }
  const nodes={}, listeners={}, calls=[], tabs=['wallets','tape','tokens','method'].map(name => { const e=new Element('button'); e.dataset.tab=name; return e; });
  const document={getElementById:id=>nodes[id] ||= new Element(),createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),querySelectorAll:()=>tabs,addEventListener:(name,fn)=>listeners['doc:'+name]=fn};
  nodes.sort=new Element('select'); nodes.sort.value='default';
  const window={document,location:{hash:''},addEventListener:(name,fn)=>listeners[name]=fn,fetch:async(path)=>{calls.push(path);return {ok,status:503,json:async()=>responseData};}};
  const context=vm.createContext({window,URL,URLSearchParams,AbortController,setTimeout,clearTimeout,setInterval:()=>0,console});
  vm.runInContext(fs.readFileSync(require.resolve('../web/research.js'),'utf8'),context);
  return {nodes,tabs,calls,window,go(hash){window.location.hash=hash;listeners.hashchange();},settle:()=>new Promise(r=>setImmediate(r)),document,listeners};
}
test('takeaway derives buy/sell counts, concentration and median only from selected fills',()=>{
 const rows=[{side:'buy',token:'a',usd:10},{side:'buy',token:'a',usd:30},{side:'buy',token:'b',usd:null},{side:'sell',token:'b',usd:20}];
 const s=ui.traderTakeaway({buys:999,net_pnl:999999},rows,[{token:'a',symbol:'ALPHA'}],'7d');
 assert.match(s,/3 buys and 1 sell/);assert.match(s,/ALPHA accounts for 2 of 3 buys \(67%/);assert.match(s,/\$20.00 across 3 of 4/);
 assert.match(s,/Interpretation:/);assert.match(s,/Study:/);assert.match(s,/Not Financial Advice\.$/);assert.ok(s.length>=500 && s.length<=800,s.length);assert.doesNotMatch(s,/999/);
});
test('takeaway handles sparse, absent and invalid data without inventing positions or intent',()=>{
 const single=ui.traderTakeaway({},[{side:'buy',token:'a',usd:12}],[],'7d');
 assert.match(single,/One fill cannot establish a pattern/);assert.match(single,/No sells appear in this sample/);
 const absent=ui.traderTakeaway({buys:28,sells:0},[],[],'7d');
 assert.match(absent,/source summary reports 28 buys and 0 sells/);assert.match(absent,/No wallet fills are loaded/);assert.match(absent,/reconcile/);
 const unknown=ui.traderTakeaway({},[{side:'unknown',usd:-4},{side:'buy',usd:'10'},{side:'sell',usd:Infinity}],[]);
 assert.match(unknown,/1 unclassified/);assert.match(unknown,/Token concentration is unavailable/);assert.match(unknown,/No usable USD estimates/);assert.doesNotMatch(unknown,/\$0.00|NaN|Infinity/);
 assert.match(ui.traderTakeaway({},[],[]),/Not Financial Advice\.$/);
});
test('every wallet opens a safe, prominent takeaway before fills, independent of optional evidence',async()=>{
 const f=fixture();f.wallets.push({address:'empty',buys:28,sells:0});const a=visitor(f);await a.settle();
 for(const id of ['test-wallet','empty','missing']){
  a.go(ui.route('wallets','wallet',id));
  const children=a.nodes.dossier.children, i=children.findIndex(n=>n.className==='trader-takeaway');
  assert.ok(i>=0);assert.equal(children[i].tagName,'section');assert.match(children[i].textContent,/Trader takeaway/);assert.doesNotMatch(children[i].textContent,/Observed:|Interpretation:|Study:/);assert.match(children[i].textContent,/Not Financial Advice\.$/);
  assert.ok(i<children.findIndex(n=>n.textContent.startsWith('Observed fills')));
 }
});
test('per-wallet history replaces fallback safely in the same top block with closed evidence',async()=>{
 const a=visitor(); await a.settle();
 a.window.fetch=async path=>({ok:true,json:async()=>path.startsWith('/api/wallet-history/')?{wallet:'test-wallet',chain_id:4663,takeaway:'Observed — ALPHA: 9 buys and 2 sells. Not Financial Advice.',groups:[{token:'x',symbol:'<script>ALPHA</script>',buys:9,sells:2,transactions:[]}],scope:{grouped:'historical, partial'},sources:{},native_history:[]}:null});
 a.go(ui.route('wallets','wallet','test-wallet')); await a.settle();
 const children=a.nodes.dossier.children, top=children.find(n=>n.className==='trader-takeaway');
 assert.match(top.textContent,/ALPHA: 9 buys and 2 sells/);
 assert.doesNotMatch(top.textContent,/loaded source-labeled/);
 const details=children.find(n=>n.tagName==='details'&&n.textContent.includes('per-wallet historical'));
 assert.ok(details); assert.notEqual(details.open,true); assert.match(details.textContent,/<script>ALPHA<\/script>/);
});
test('display copy removes only structural signposts, keeping evidence and qualifiers',()=>{
 const source='Observed — ALPHA: 9 buys and 2 sells. Interpretation: may suggest repeated entries, not a proven rule. Study: compare dated sales. Not Financial Advice.';
 assert.equal(ui.readableTakeaway(source),'ALPHA: 9 buys and 2 sells. may suggest repeated entries, not a proven rule. To explore this, compare dated sales. Not Financial Advice.');
 assert.equal(ui.readableTakeaway('Token Observed: source label remains.'),'Token Observed: source label remains.');
});
test('wallet evidence and fill rows are closed while an admitted experiment link stays visible',async()=>{
 const a=visitor();await a.settle();
 a.window.fetch=async path=>({ok:true,json:async()=>path==='/api/hypothesis-replay'?{status:'completed',evaluation_kind:'retrospective',seed_count:1,replay:{generations:[{flies:[{seed_origin:{provenance:{wallet:'test-wallet'}}}]}]}}:path==='/api/research'?fixture():null});
 await a.nodes.refresh.onclick();await a.settle();a.go(ui.route('wallets','wallet','test-wallet'));await a.settle();
 const children=a.nodes.dossier.children, details=children.filter(n=>n.tagName==='details');
 assert.ok(details.some(n=>n.textContent.includes('wallet → experiment')));
 assert.ok(details.some(n=>n.textContent.includes('supported rules')));
 assert.ok(details.some(n=>n.textContent.includes('fixture-fill')));
 assert.ok(details.every(n=>n.open!==true));
 const watch=children.find(n=>n.tagName==='a'&&n.textContent==='Watch wallet experiment ↗');
 assert.equal(watch?.href,'/?replay=hypothesis&wallet=test-wallet');
 assert.ok(children.some(n=>n.tagName==='p'&&n.textContent.includes('exits assumed')));
});
test('formatting preserves signs, unknown values and zero',()=>{
  assert.equal(ui.money(-10,true),'−$10.00');assert.equal(ui.money(10,true),'+$10.00');assert.equal(ui.money(0,true),'$0.00');assert.equal(ui.money(null),'—');assert.equal(ui.money('10'),'—');assert.equal(ui.money(Infinity),'—');
});
test('snapshot age is explicit, stale and clock mismatch are distinguishable',()=>{
 const ts=Date.parse('2026-09-14T19:00:00Z');assert.match(ui.freshness(ts,ts+16*60000),/^STALE/);assert.match(ui.freshness(ts,ts+60000),/1m old/);assert.match(ui.freshness(null),/Unknown/);assert.match(ui.freshness(ts,ts-120000),/Clock mismatch/);
});
test('hash dossier links round-trip hostile labels as data, reject extra views',()=>{
 const id='wallet&token=<script>#';assert.deepEqual(ui.parseHash(ui.route('tape','wallet',id)),{tab:'tape',kind:'wallet',id});assert.equal(ui.parseHash('#view=arena').tab,'wallets');
});
test('normalize requires real arrays, filtering does not use unrelated global metrics',()=>{
 assert.throws(()=>ui.normalize({wallets:[]}),/Invalid/);const f=ui.normalize(fixture());assert.equal(f.wallets.length,1);assert.equal(ui.rowsFor(f,'wallets','test-wallet','default').length,1);assert.equal(ui.rowsFor(f,'tokens','missing','default').length,0);assert.equal(ui.matchingFills(f,'wallet','unknown').length,0);
});
test('rules require supporting IDs in this wallet sample; no synthetic candle series',()=>{
 const f=fixture(); const wallet={observed_rules:[{description:'supported fixture',fill_ids:['fixture-fill']},{description:'unsupported fixture',fill_ids:['missing']},{description:'no evidence'}]};assert.equal(ui.supportedRules(wallet,f.fills).length,1);assert.equal(ui.supportedRules(wallet,[]).length,0);assert.deepEqual(ui.candlesOf(f.tokens[0]),[]);assert.equal(ui.candlesOf({candles:[[1789412400,1,2,0,1.5,5],{ts:1789412500,close:2}]}).length,2);assert.equal(ui.safeURL('javascript:alert(1)'),null);assert.equal(ui.safeURL('https://user:pass@example.org'),null);
});
test('real UI fetches only research API and safely renders API rows and actual counts',async()=>{
 const a=visitor();await a.settle();assert.deepEqual(a.calls.slice().sort(),['/api/hypothesis-replay','/api/research','/api/wallet-replay']);assert.equal(a.nodes['wallet-count'].textContent,'1');assert.equal(a.nodes['fill-count'].textContent,'1');assert.equal(a.nodes['token-count'].textContent,'1');assert.match(a.nodes.results.textContent,/<img src=x onerror=alert\(1\)>/);assert.match(a.nodes.results.textContent,/−\$10.00/);assert.match(a.nodes.results.textContent,/25%/);assert.match(a.nodes.warnings.textContent,/TEST FIXTURE/);assert.equal(a.nodes['research-panel'].attributes['aria-busy'],'false');
 a.go(ui.route('wallets','wallet','test-wallet'));assert.equal(a.nodes.dossier.hidden,false);assert.match(a.nodes.dossier.textContent,/fixture-fill/);assert.match(a.nodes.dossier.textContent,/Insufficient validated history/);assert.match(a.nodes.dossier.textContent,/No exact wallet-to-fly mapping/);
 a.go(ui.route('tokens','token','test-token'));assert.match(a.nodes.dossier.textContent,/No usable candle series/);assert.match(a.nodes.results.textContent,/DRAINED/);
 a.go('#view=method');assert.equal(a.nodes.dossier.hidden,true);assert.match(a.nodes.results.textContent,/PnL is not executable profit/);
});
test('empty, loading/error retry and filter states are explicit',async()=>{
 const a=visitor({...fixture(),wallets:[],fills:[],tokens:[]});await a.settle();assert.match(a.nodes.results.textContent,/No wallets rows supplied/);
 const b=visitor(fixture(),false);await b.settle();assert.match(b.nodes.status.textContent,/HTTP 503/);assert.match(b.nodes.results.textContent,/no demo data/i);assert.equal(b.nodes.refresh.disabled,false);
 const c=visitor();await c.settle();c.nodes.search.value='nonexistent';c.nodes.search.oninput();assert.match(c.nodes.results.textContent,/No matches/);
});
test('tab keyboard navigation, escape close and bounded pagination',async()=>{
 const f=fixture();f.wallets=Array.from({length:51},(_,i)=>({...f.wallets[0],address:'fixture-'+i}));const a=visitor(f);await a.settle();assert.match(a.nodes.pagination.textContent,/1–50 \/ 51/);a.nodes.pagination.children[2].click();assert.match(a.nodes.pagination.textContent,/51–51 \/ 51/);
 let prevented=false;a.tabs[0].onkeydown({key:'End',preventDefault(){prevented=true;}});assert.equal(prevented,true);assert.equal(a.window.location.hash,'#view=method');assert.equal(a.tabs[3].focused,true);
 a.go(ui.route('wallets','wallet','fixture-0'));a.listeners['doc:keydown']({key:'Escape'});assert.equal(a.window.location.hash,'#view=wallets');
});
