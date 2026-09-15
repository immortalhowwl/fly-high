/* Source observation only. These flies filter evidence; they never place trades. */
(function(root){
 'use strict';
 const doc=root.document,$=id=>doc.getElementById(id),names={trader:'FOLLOW TRADER',group:'FOLLOW GROUP',exits:'WATCH EXITS'};
 let data=null,mode='trader',wallet='',selected=null,limit=40;
 const el=(tag,text,cls)=>{const e=doc.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
 const short=s=>s?s.slice(0,8)+'…'+s.slice(-6):'Not supplied';
 const date=v=>v==null?'Not supplied':new Date(typeof v==='number'?v*1000:v).toISOString().replace('T',' ').replace(/\.\d+Z$/,' UTC');
 const usd=v=>typeof v==='number'&&Number.isFinite(v)?'$'+v.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'Not supplied';
 function link(label,url){const a=el('a',label);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;}
 function walletLink(address){return link('Wallet breakdown ↗','/research#view=wallets&wallet='+encodeURIComponent(address));}
 function selectMode(next){mode=next;selected=null;limit=40;render();}
 function eventDetail(e){
  const block=el('article',undefined,'obs-evidence');
  block.append(el('h3',e.side.toUpperCase()+' · '+e.symbol),el('p',e.handle+' · '+short(e.wallet)),el('p',date(e.ts)),el('p','Source-estimated trade value: '+usd(e.usd)));
  const links=el('div',undefined,'obs-links');links.append(walletLink(e.wallet),link('Token on explorer ↗','https://robinhoodchain.blockscout.com/token/'+e.token));
  if(/^https:\/\/robinhoodchain\.blockscout\.com\/tx\/0x[0-9a-fA-F]{64}$/.test(e.transaction_url||''))links.append(link('Transaction ↗',e.transaction_url));
  else block.append(el('p','No transaction hash supplied for this event.'));
  block.append(links);
  if(e.flags?.length)block.append(el('p','Source flags: '+(Array.isArray(e.flags)?e.flags.join(' · '):e.flags),'obs-warning'));
  const details=el('details');details.append(el('summary','Event evidence'),el('p','Indexer event '+e.id+' · source cash-leg classification, not independently receipt-verified.'),el('p','Wallet: '+e.wallet),el('p','Token: '+e.token));block.append(details);return block;
 }
 function inspect(item){
  selected=mode==='group'?item.token:item.id;
  const panel=$('obs-detail');panel.replaceChildren(el('p',names[mode]+' / RULE MATCH','eyebrow'));
  if(mode==='group'){
   panel.append(el('h2',item.symbol),el('p',item.wallets.length+' distinct tracked wallets bought this token in the displayed window. Repeated buys do not increase the wallet count.'));
   const identities=el('div',undefined,'obs-group-wallets');
   for(const address of item.wallets){const w=data.roster.find(w=>w.address===address);const b=el('button','Follow '+(w?.handle||short(address)));b.onclick=()=>{wallet=address;$('obs-wallet').value=address;selectMode('trader');};identities.append(b);}
   panel.append(identities,el('h3','Qualifying purchases'));
   const ids=new Set(item.event_ids);for(const e of data.events.filter(e=>ids.has(e.id)))panel.append(eventDetail(e));
   const sales=data.exits.filter(e=>e.token===item.token);const exitDetails=el('details');exitDetails.append(el('summary',sales.length+' sales of this token by the same roster in this window'));
   for(const e of sales)exitDetails.append(eventDetail(e));panel.append(exitDetails);
  }else panel.append(eventDetail(item));
  for(const row of $('obs-feed').children)row.setAttribute('aria-pressed',row.dataset.key===selected?'true':'false');
 }
 function render(){
  if(!data)return;
  for(const key of Object.keys(names))$('fly-'+key).setAttribute('aria-pressed',key===mode?'true':'false');
  $('obs-wallet-control').hidden=mode!=='trader';$('obs-rule').textContent=data.rules[mode];$('obs-feed-title').textContent=names[mode]+' / MATCHES';
  const rows=mode==='group'?data.groups:mode==='exits'?data.exits:data.events.filter(e=>e.wallet===wallet);
  $('obs-match-count').textContent=rows.length+(mode==='group'?' qualifying tokens':' source events');
  $('trader-count').textContent=data.events.filter(e=>e.wallet===wallet).length+' events · selected wallet';
  $('group-count').textContent=data.groups.length+' tokens · ≥2 wallets';$('exits-count').textContent=data.exits.length+' sales · tracked roster';
  const feed=$('obs-feed');feed.replaceChildren();$('obs-detail').replaceChildren(el('p','Select a match to inspect its wallets, token and source evidence.'));
  for(const item of rows.slice(0,limit)){
   const button=el('button',undefined,'obs-match');button.dataset.key=mode==='group'?item.token:item.id;
   if(mode==='group')button.append(el('strong',item.symbol),el('span',item.wallets.length+' distinct wallets · '+item.event_ids.length+' buys'),el('small',date(item.last_ts)));
   else button.append(el('strong',item.side.toUpperCase()+' · '+item.symbol,item.side==='sell'?'obs-sell':'obs-buy'),el('span',item.handle+' · '+usd(item.usd)),el('small',date(item.ts)));
   button.onclick=()=>inspect(item);feed.append(button);
  }
  $('obs-more').hidden=rows.length<=limit;$('obs-more').textContent='Show more ('+Math.max(0,rows.length-limit)+' remaining)';
  if(!rows.length)feed.append(el('p','No qualifying '+(mode==='group'?'two-wallet purchase groups':mode==='exits'?'sales':'buys or sells for this wallet')+' in this source window. Missing matches are not proof of inactivity.','obs-empty'));
  else inspect(rows.find(r=>(mode==='group'?r.token:r.id)===selected)||rows[0]);
  $('obs-wallet-breakdown').href='/research#view=wallets&wallet='+encodeURIComponent(wallet);
 }
 async function load(){
  $('obs-refresh').disabled=true;$('obs-status').textContent=data?'Refreshing source snapshot…':'Loading source observations…';
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  try{
   const response=await root.fetch('/api/observations',{signal:controller.signal});if(!response.ok)throw Error('Source unavailable');
   data=await response.json();
   const requested=new URLSearchParams(root.location.search).get('wallet');
   if(!data.roster.some(w=>w.address===wallet))wallet=data.roster.find(w=>w.address===requested)?.address||data.events[0]?.wallet||data.roster[0]?.address||'';
   const select=$('obs-wallet');select.replaceChildren();
   for(const w of [...data.roster].sort((a,b)=>a.handle.localeCompare(b.handle))){const o=el('option',w.handle+' · '+w.events+' events');o.value=w.address;select.append(o);}select.value=wallet;
   $('obs-status').textContent=(data.source.stale?'STALE SOURCE · ':'SOURCE SNAPSHOT · ')+data.source.name+' · captured '+date(data.source.captured_at);
   $('obs-window').textContent='Event window: '+date(data.window.since)+' → '+date(data.window.until)+' · latest bounded tape, not a complete 7-day history.';
   $('obs-coverage').textContent=data.counts.roster+' tracked wallets · '+data.counts.events+' admitted / '+data.counts.source_rows+' source rows · '+data.counts.excluded_or_duplicate+' excluded or duplicate rows. Roster comes from the current research snapshot; no arbitrary wallet scanning.';
   $('obs-limits').textContent=data.limits;
   $('obs-source-link').href='https://robinhoodtrenches.com/api/tape?limit=500&stocks=false';
   render();
  }catch(error){$('obs-status').textContent=data?'Refresh unavailable. Showing previous snapshot with its original timestamps.':'Observations unavailable. Retry to load source evidence; no demo trades substituted.';}
  finally{clearTimeout(timer);$('obs-refresh').disabled=false;}
 }
 for(const key of Object.keys(names))$('fly-'+key).onclick=()=>selectMode(key);
 $('obs-wallet').onchange=()=>{wallet=$('obs-wallet').value;selected=null;limit=40;render();};
 $('obs-more').onclick=()=>{limit+=40;render();};$('obs-refresh').onclick=load;
 load();
})(window);
