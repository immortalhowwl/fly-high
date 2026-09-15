/* Read-only upstream research and optional precomputed seed admission. No invented rows or execution. */
(function (root) {
  'use strict';
  const TABS = ['wallets', 'tape', 'tokens', 'method'], PAGE = 50;
  const number = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
  const text = value => value == null ? 'Not supplied' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
  const short = value => typeof value === 'string' && value.length > 18 ? value.slice(0, 8) + '…' + value.slice(-6) : text(value);
  function money(value, signed = false) {
    const n = number(value);
    return n === null ? '—' : (n < 0 ? '−' : signed && n > 0 ? '+' : '') + '$' + Math.abs(n).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }
  function epoch(value) {
    if (typeof value === 'number') return value < 1e12 ? value * 1000 : value;
    return typeof value === 'string' ? Date.parse(value) : NaN;
  }
  function date(value) {
    const n = epoch(value);
    return Number.isFinite(n) ? new Date(n).toISOString().replace('T', ' ').replace(/\.\d+Z$/, ' UTC') : 'Not supplied';
  }
  function freshness(value, now = Date.now()) {
    const ts = epoch(value);
    if (!Number.isFinite(ts)) return 'Unknown snapshot age';
    const seconds = Math.floor((now - ts) / 1000);
    if (seconds < -60) return 'Clock mismatch · future timestamp';
    const minutes = Math.floor(Math.max(0, seconds) / 60);
    return (minutes >= 15 ? 'STALE · ' : 'Snapshot · ') + (minutes < 60 ? minutes + 'm old' : Math.floor(minutes / 60) + 'h ' + minutes % 60 + 'm old');
  }
  function parseHash(hash) {
    const params = new URLSearchParams(hash.replace(/^#/, ''));
    const tab = TABS.includes(params.get('view')) ? params.get('view') : 'wallets';
    return {tab, kind: params.has('wallet') ? 'wallet' : params.has('token') ? 'token' : null, id: params.get('wallet') || params.get('token') || null};
  }
  function route(tab, kind, id) {
    const p = new URLSearchParams({view: TABS.includes(tab) ? tab : 'wallets'});
    if (['wallet', 'token'].includes(kind) && typeof id === 'string' && id) p.set(kind, id);
    return '#' + p.toString();
  }
  function normalize(data) {
    if (!data || typeof data !== 'object' || !['wallets', 'fills', 'tokens'].every(key => Array.isArray(data[key]))) throw new Error('Invalid research response: expected wallets, fills and tokens arrays.');
    return {...data, wallets: data.wallets.filter(x => x && typeof x === 'object'), fills: data.fills.filter(x => x && typeof x === 'object'), tokens: data.tokens.filter(x => x && typeof x === 'object'), warnings: Array.isArray(data.warnings) ? data.warnings : []};
  }
  function matchingFills(data, kind, id) {
    return data.fills.filter(fill => fill[kind === 'wallet' ? 'wallet' : 'token'] === id).sort((a,b) => (epoch(b.ts) || 0) - (epoch(a.ts) || 0));
  }
  function rowsFor(data, tab, query, sort) {
    let rows = (tab === 'tape' ? data.fills : tab === 'tokens' ? data.tokens : data.wallets).filter(row => [row.address, row.handle, row.wallet, row.token, row.symbol, row.name, row.tx, row.side].some(v => typeof v === 'string' && v.toLowerCase().includes(query.toLowerCase())) || !query);
    if (sort !== 'default') rows = [...rows].sort((a,b) => (number(b[sort]) ?? -Infinity) - (number(a[sort]) ?? -Infinity));
    return rows;
  }
  // A rule is displayable only when its evidence points to fills in this response.
  function supportedRules(wallet, fills) {
    const ids = new Set(fills.map(f => String(f.id)));
    return (Array.isArray(wallet.observed_rules) ? wallet.observed_rules : []).filter(rule => rule && typeof rule === 'object' && typeof rule.description === 'string' && Array.isArray(rule.fill_ids) && rule.fill_ids.length && rule.fill_ids.every(id => ids.has(String(id))));
  }
  // Descriptive only: selected /api/research rows, never inferred inventory or replay output.
  function traderTakeaway(wallet = {}, fills = [], tokens = [], window = 'reported window') {
    const count = (n, word) => n + ' ' + word + (n === 1 ? '' : 's');
    if (!fills.length) {
      const known = n => Number.isInteger(n) && n >= 0;
      const summary = known(wallet?.buys) && known(wallet?.sells)
        ? ' The source summary reports ' + count(wallet.buys, 'buy') + ' and ' + count(wallet.sells, 'sell') + ' for ' + text(window) + '; these are not loaded fill counts.' : ' No usable buy/sell totals are supplied either.';
      return 'Observed: No wallet fills are loaded in this bounded tape.' + summary + ' Token concentration and typical estimated size cannot be checked here. Interpretation: this is a coverage gap, not evidence of inactivity or a holding strategy. Study: obtain this wallet’s dated fills and reconcile them with the summary before comparing repeated entries, sale activity or order sizes. Summary PnL alone cannot explain how a result was achieved. Not Financial Advice.';
    }
    const nonTrades = fills.filter(f => f.priced === 'no_cash_leg' || (Array.isArray(f.flags) && f.flags.some(flag => /not a real (buy|sell)|airdrop|transferred/i.test(String(flag)))));
    if (nonTrades.length) {
      const valid = fills.filter(f => !nonTrades.includes(f)), b = valid.filter(f => f.side === 'buy'), s = valid.filter(f => f.side === 'sell');
      const names = [...new Set(nonTrades.map(f => f.symbol).filter(x => typeof x === 'string'))].slice(0, 3).map(x => x.slice(0, 24)).join(', ');
      const observation = 'Observed: ' + fills.length + ' source rows are loaded. ' + nonTrades.length + ' are marked as airdrops/transfers or have no cash leg' + (names ? ' (' + names + ')' : '') + '; their USD estimates are not confirmed spending. ';
      const remainder = valid.length ? 'Excluding those leaves ' + count(b.length, 'buy') + ' and ' + count(s.length, 'sell') + ' labeled by the source. ' : 'None of the loaded rows establishes a cash-funded trade. ';
      const meaning = valid.length ? 'Interpretation: separate these remaining events from incoming token distributions; mixing them would distort entry counts and trade size. ' : 'Interpretation: repeated incoming tokens here are not evidence of repeated buying or conviction. This sample cannot explain the wallet’s trading approach. ';
      return observation + remainder + meaning + 'Study: verify the cash leg and token sellability, then match genuine buys to later sales. Do not use marked token values as invested capital or a model position size. Not Financial Advice.';
    }
    const buys = fills.filter(f => f.side === 'buy'), sells = fills.filter(f => f.side === 'sell');
    const unknown = fills.length - buys.length - sells.length;
    const priced = fills.map(f => number(f.usd)).filter(n => n !== null && n >= 0).sort((a,b) => a-b);
    const mid = Math.floor(priced.length / 2), median = priced.length % 2 ? priced[mid] : priced[mid-1] / 2 + priced[mid] / 2;
    const counts = new Map();
    buys.forEach(f => { if (typeof f.token === 'string' && f.token) counts.set(f.token, (counts.get(f.token) || 0) + 1); });
    const ranked = [...counts].sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0]));
    const top = ranked[0], identified = [...counts.values()].reduce((a,b) => a+b, 0);
    const rawLabel = top && (tokens.find(t => (t.token || t.address) === top[0])?.symbol || buys.find(f => f.token === top[0])?.symbol || short(top[0]));
    const label = typeof rawLabel === 'string' ? rawLabel.slice(0, 32) : top ? short(top[0]) : '';
    const concentration = top ? label + ' accounts for ' + top[1] + ' of ' + buys.length + ' buys (' + Math.round(top[1] / buys.length * 100) + '% by count, not capital).' + (identified < buys.length ? ' Some token IDs are missing.' : '') : 'Token concentration is unavailable without identified buys.';
    const size = priced.length ? 'Median source-estimated size is ' + money(median) + ' across ' + priced.length + ' of ' + fills.length + ' fills' + (priced.length > 1 ? ', ranging from ' + money(priced[0]) + ' to ' + money(priced[priced.length - 1]) : '') + '; this is not portfolio sizing.' : 'No usable USD estimates are loaded; trade size cannot be compared.';
    const interpretation = fills.length === 1 ? 'One fill cannot establish a pattern.' : top?.[1] > 1 ? 'Repeated buy labels suggest recurring activity in ' + label + ', not a proven entry rule.' : 'These rows show activity, not a repeatable strategy.';
    const activity = sells.length === 0 ? 'No sells appear in this sample; that does not prove holding.' : buys.length === 0 ? 'Sales without loaded buys cannot establish entry cost or profit.' : 'Both sides appear, but a sell does not prove a full exit or profit.';
    const study = top?.[1] > 1 ? 'compare the repeated buys’ timestamps and sizes, then check later sales in the same token; do not copy the size.' : buys.length && sells.length ? 'match buys and sells by token and time before testing any entry/exit hypothesis.' : buys.length ? 'look for further buys of the same token and dated sales before testing a repeat-entry hypothesis.' : sells.length ? 'trace the sales back to earlier purchases before studying exit timing.' : 'verify the unclassified events’ sides and token IDs before comparing entries or sales.';
    const flagged = fills.some(f => Array.isArray(f.flags) && f.flags.length);
    return 'Observed: ' + fills.length + ' loaded source-labeled fills: ' + count(buys.length, 'buy') + ' and ' + count(sells.length, 'sell') + (unknown ? '; ' + unknown + ' unclassified' : '') + '. ' + concentration + ' ' + size + (flagged ? ' Source flags require checking; labels may not be real trades.' : '') + ' Interpretation: ' + interpretation + ' ' + activity + ' Study: ' + study + ' Not Financial Advice.';
  }
  // Remove only template signposts at sentence boundaries, never evidence or qualifiers.
  function readableTakeaway(value) {
    return String(value).replace(/(^|[.!?]\s+|\n\s*)(Observed|Interpretation|Study)\s*(?::|—|–)\s*/g,
      (_, boundary, label) => boundary + (label === 'Study' ? 'To explore this, ' : ''));
  }
  function safeURL(value) {
    try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null; } catch (_) { return null; }
  }
  function candlesOf(token) {
    return (Array.isArray(token.candles) ? token.candles : []).map(c => ({ts: epoch(Array.isArray(c) ? c[0] : c.ts), close: number(Array.isArray(c) ? c[4] : c.close)})).filter(c => Number.isFinite(c.ts) && c.close !== null && c.close >= 0).sort((a,b) => a.ts - b.ts);
  }
  function candleSegments(candles) {
    const segments = [];
    candles.forEach((c, i) => {
      if (!i || c.ts - candles[i - 1].ts > 300000) segments.push([]);
      segments[segments.length - 1].push(c);
    });
    return segments;
  }
  function priceUSD(value) { return '$' + value.toPrecision(5); }
  function walletReplayLink(envelope, wallet) {
    if (!wallet || envelope?.status !== 'completed' || !Number.isInteger(envelope.seed_count) || envelope.seed_count < 1) return null;
    const founders = envelope.replay?.generations?.[0]?.flies || [];
    return founders.some(f => f.seed_origin?.provenance?.wallet === wallet) ? '/?replay=wallet&wallet=' + encodeURIComponent(wallet) : null;
  }
  function hypothesisReplayLink(envelope,wallet){
    if(envelope?.evaluation_kind !== 'retrospective')return null;
    return walletReplayLink(envelope,wallet)?.replace('replay=wallet','replay=hypothesis') || null;
  }
  const api = {readableTakeaway, traderTakeaway, candleSegments, priceUSD, walletReplayLink, hypothesisReplayLink, money, epoch, date, freshness, parseHash, route, normalize, rowsFor, matchingFills, supportedRules, safeURL, candlesOf};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (!root.document) return;
  const doc = root.document, $ = id => doc.getElementById(id);
  let replayEnvelope = null, hypothesisEnvelope = null, replayRequest = 0;
  let behaviorReport = null, behaviorState = "idle", behaviorRequest = 0;
  let data = null, state = parseHash(root.location.hash), page = 0, loading = false;
  function el(tag, value, cls) { const node = doc.createElement(tag); if (value != null) node.textContent = String(value); if (cls) node.className = cls; return node; }
  function link(value, href, cls) { const a = el('a', value, cls); a.href = href; return a; }
  function signed(value) { return number(value) === null || value === 0 ? '' : value > 0 ? 'positive' : 'negative'; }
  function entity(kind, id, label) { return id ? link(label || short(id), route(state.tab, kind, String(id))) : el('span', label || 'Unknown'); }
  function stat(label, value, cls) { const box = el('div', null, 'stat'); box.append(el('span', label, 'label'), el('strong', value, cls)); return box; }
  function showStatus(message, error = false) { $('status').textContent = message; $('status').className = error ? 'status error' : 'status'; }
  function header() {
    $('source').textContent = typeof data.source === 'object' && data.source ? text(data.source.name || data.source.url) : text(data.source); $('window').textContent = text(data.window);
    $('as-of').textContent = date(data.as_of); $('freshness').textContent = freshness(data.as_of);
    $('freshness').className = /STALE|Unknown|mismatch/.test($('freshness').textContent) ? 'negative' : '';
    $('wallet-count').textContent = String(data.wallets.length); $('fill-count').textContent = String(data.fills.length); $('token-count').textContent = String(data.tokens.length);
    $('warnings').replaceChildren(...data.warnings.map(warning => el('p', text(warning)))); $('warnings').hidden = !data.warnings.length;
  }
  function table(headers, rows, render, caption) {
    const wrap = el('div', null, 'table-wrap'); wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', caption + ' (scroll horizontally for all columns)');
    const t = el('table'), head = el('thead'), tr = el('tr'), body = el('tbody');
    headers.forEach(label => { const th = el('th', label); th.scope = 'col'; tr.append(th); }); head.append(tr);
    rows.forEach(row => { const line = el('tr'); render(row).forEach(value => { const td = el('td'); if (value && typeof value === 'object') td.append(value); else td.textContent = text(value); line.append(td); }); body.append(line); });
    t.append(el('caption', caption), head, body); wrap.append(t); return wrap;
  }
  function pnl(value) { return el('span', money(value, true), 'num ' + signed(value)); }
  function walletName(row) { const node = el('div'); node.append(entity('wallet', row.address, row.handle || short(row.address)), el('span', short(row.address), 'secondary')); return node; }
  function tokenName(row) { const node = el('div'); node.append(entity('token', row.token || row.address, row.symbol || row.name || short(row.token || row.address)), el('span', short(row.token || row.address), 'secondary')); return node; }
  function fillCells(row) { return [date(row.ts), entity('wallet', row.wallet, data.wallets.find(w => w.address === row.wallet)?.handle || short(row.wallet)), entity('token', row.token, row.symbol || short(row.token)), el('span', text(row.side).toUpperCase(), row.side === 'buy' ? 'positive' : row.side === 'sell' ? 'negative' : ''), money(row.usd), number(row.amount) === null ? '—' : row.amount.toLocaleString('en-US', {maximumSignificantDigits: 7}), short(row.tx)]; }
  function renderList() {
    const rows = rowsFor(data, state.tab, $('search').value, $('sort').value);
    const maxPage = Math.max(0, Math.ceil(rows.length / PAGE) - 1); page = Math.min(page, maxPage);
    const subset = rows.slice(page * PAGE, (page + 1) * PAGE), caption = rows.length + ' matching rows · ' + (state.tab === 'wallets' ? 'PnL and win rate reported by source, not reconstructed from the loaded tape' : state.tab === 'tokens' ? 'Source-reported token summary; liquidity is not an executable price' : 'Observed source fills · not Colony executions');
    $('results').replaceChildren(); $('pagination').replaceChildren();
    if (!rows.length) { $('results').append(el('div', $('search').value ? 'No matches in this snapshot. Clear the filter to see all loaded rows.' : 'No ' + state.tab + ' rows supplied. Nothing has been simulated to fill this view.', 'empty')); return; }
    let node;
    if (state.tab === 'wallets') node = table(['Wallet / handle', 'Realized USD', 'Unrealized USD', 'Net USD', 'Source fills', 'Win rate'], subset, row => [walletName(row), pnl(row.realized_pnl), pnl(row.unrealized_pnl), pnl(row.net_pnl), number(row.fills) === null ? '—' : row.fills.toLocaleString('en-US'), number(row.win_rate) === null ? '—' : (row.win_rate * 100).toLocaleString('en-US', {maximumFractionDigits: 2}) + '%'], caption);
    else if (state.tab === 'tokens') node = table(['Token', 'Buyers', 'Bought USD', 'Sold USD', 'Liquidity USD', 'Source flags'], subset, row => [tokenName(row), number(row.buyers) ?? '—', money(row.usd_in), money(row.usd_out), money(row.liquidity), el('span', row.honeypot ? 'HONEYPOT FLAG' : row.drained ? 'DRAINED' : row.parked ? 'PARKED' : 'Not flagged ≠ safe', 'badge ' + (row.honeypot || row.drained ? 'risk' : ''))], caption);
    else node = table(['Time / UTC', 'Wallet', 'Token', 'Side', 'USD notional', 'Token amount', 'Transaction'], subset, fillCells, caption);
    $('results').append(node);
    const prev = el('button', '← Previous'), next = el('button', 'Next →'); prev.type = next.type = 'button'; prev.disabled = page === 0; next.disabled = page >= maxPage;
    prev.onclick = () => { page--; renderList(); }; next.onclick = () => { page++; renderList(); };
    $('pagination').append(prev, el('span', (page * PAGE + 1) + '–' + Math.min((page + 1) * PAGE, rows.length) + ' / ' + rows.length), next);
  }
  function method() {
    const section = el('div', null, 'method'); section.append(el('h2', 'What this research can — and cannot — tell you'));
    const items = [
      ['01 / Data provenance', 'Read-only /api/research snapshot. Wallet identity, PnL, token marks and fills are upstream indexer claims unless per-record validation is explicitly supplied. A transaction hash is a reference, not proof that this UI independently checked a receipt.'],
      ['02 / Coverage and window', 'The research requests a ' + text(data.window) + ' window from the data provider. This is a limited sample, not a complete trading history. The trade feed contains the latest available trades and may not cover that entire period.\nWallet trade totals and token buyer counts may refer to more records than are loaded on this page.'],
      ['03 / PnL is not executable profit', 'Realized, unrealized and net PnL are shown separately as reported. Win rate is source-reported in percent. Unknown values stay blank (—), not zero. Marks, thin liquidity, missing fees and incomplete opening inventory can make returns misleading. A sell alone does not prove a full exit.'],
      ['04 / Evidence before rules', 'Wallet dossiers show only observed rules with supporting fill IDs present in the loaded wallet tape. Missing or incomplete history means insufficient validated history, not an inferred strategy. Behavioural descriptions do not establish trading intent or predictive skill.'],
      ['05 / Freshness', 'Snapshot age is time since as_of, not time since the latest on-chain fill and not a polling SLA. This UI labels snapshots at least 15 minutes old STALE. Refresh explicitly fetches a new response; it cannot make an upstream archive live.'],
      ['06 / Research ≠ Colony execution', 'Colony is a separate simulation/replay surface. A wallet replay link appears only when that wallet is present as an admitted founder in the precomputed replay. Canonical allocation evidence is separate from indexer tape; other genes may retain defaults. Opening a replay does not copy a wallet or execute a trade. No wallet connection, trading orders or Telegram access are implemented in this portal.'],
      ['07 / Token charts', 'A price line is drawn only from actual timestamped OHLCV candles supplied for the selected token. No candles means no chart. Token summary marks are not a time series. Risk flags come from the source; their absence is not a safety assessment.']
    ];
    items.forEach(([title, description]) => { const article = el('article'); article.append(el('h3', title), el('p', description)); section.append(article); });
    $('results').replaceChildren(section); $('pagination').replaceChildren();
  }
  function detailFills(box, fills) {
    box.append(el('h3', 'Observed fills · ' + fills.length + ' loaded'));
    if (!fills.length) box.append(el('p', 'No fills for this selection in the loaded sample. This does not prove inactivity.'));
    // Every selected fill is accessible; disclosure groups keep large dossiers usable.
    for (let start = 0; start < fills.length; start += 25) {
      const group = el('details');
      group.append(el('summary', 'Rows ' + (start + 1) + '–' + Math.min(start + 25, fills.length)));
      fills.slice(start, start + 25).forEach(fill => {
        const row = el('div', null, 'detail-fill'); row.append(el('span', text(fill.side).toUpperCase() + ' ' + money(fill.usd) + ' · ', fill.side === 'sell' ? 'negative' : ''), entity('token', fill.token, fill.symbol || short(fill.token)), el('span', ' / '), entity('wallet', fill.wallet, data.wallets.find(w => w.address === fill.wallet)?.handle || short(fill.wallet)), el('span', date(fill.ts), 'secondary'), el('span', 'Fill ' + text(fill.id), 'secondary'), el('span', 'Tx: ' + text(fill.tx), 'secondary')); group.append(row);
      }); box.append(group);
    }
  }
  function chart(box, token) {
    const candles = candlesOf(token);
    box.append(el('h3', 'Price history'));
    if (candles.length < 2) { box.append(el('p', 'No usable candle series supplied. A quoted mark is not a chart.')); return; }
    const min = Math.min(...candles.map(c => c.close)), max = Math.max(...candles.map(c => c.close));
    const start = candles[0].ts, duration = candles[candles.length - 1].ts - start;
    if (!duration) { box.append(el('p', 'Insufficient distinct candle timestamps for a chart.')); return; }
    const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 420 180'); svg.setAttribute('class', 'chart'); svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', 'USD closed candle prices; gaps over five minutes are not connected');
    const point = c => [90 + (c.ts - start) / duration * 318, max === min ? 80 : 140 - (c.close - min) / (max - min) * 122];
    candleSegments(candles).forEach(segment => {
      const line = doc.createElementNS(svg.namespaceURI, 'polyline');
      line.setAttribute('points', segment.map(c => point(c).join(',')).join(' '));
      line.setAttribute('fill', 'none'); line.setAttribute('stroke', 'currentColor'); line.setAttribute('stroke-width', '2'); svg.append(line);
      if (segment.length === 1) {
        const dot = doc.createElementNS(svg.namespaceURI, 'circle'), xy = point(segment[0]);
        dot.setAttribute('cx', xy[0]); dot.setAttribute('cy', xy[1]); dot.setAttribute('r', '2'); dot.setAttribute('fill', 'currentColor'); svg.append(dot);
      }
    });
    [[max, 20], [(min + max) / 2, 80], [min, 140]].forEach(([value, y]) => {
      const label = doc.createElementNS(svg.namespaceURI, 'text');
      label.setAttribute('x', '2'); label.setAttribute('y', y); label.setAttribute('fill', 'currentColor'); label.setAttribute('font-size', '11'); label.textContent = priceUSD(value); svg.append(label);
    });
    box.append(svg, el('p', date(start) + ' → ' + date(candles[candles.length - 1].ts)), el('p', 'USD close range: ' + priceUSD(min) + ' – ' + priceUSD(max)));
    const source = token.chart_source || {};
    box.append(el('p', candles.length + ' actual 5-minute closes · ' + text(source.provider || source) + ' · ' + (source.stale ? 'STALE' : 'Saved snapshot')),
      el('p', 'As of ' + date(source.as_of) + ' · Collected ' + date(source.collected_at)),
      el('p', 'Gaps >300s: ' + (source.gaps_over_300_seconds ?? 'unknown') + ' · Not connected or interpolated. ' + text(source.warning)));
    const url = safeURL(source.url);
    if (url) { const a = link('GeckoTerminal OHLCV source ↗', url); a.target = '_blank'; a.rel = 'noopener noreferrer'; box.append(a); }
  }
  function loadBehavior() {
    if (behaviorState !== 'idle') return;
    behaviorState = 'loading';
    const request = ++behaviorRequest;
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
    root.fetch('/api/behavior', {cache: 'no-store', signal: controller.signal})
      .then(r => r.ok ? r.json() : null)
      .then(report => {
        if (request !== behaviorRequest) return;
        behaviorReport = report && ['hypotheses_available', 'features_only'].includes(report.status) && Array.isArray(report.wallets) && Array.isArray(report.candidates) ? report : null;
        behaviorState = behaviorReport ? 'loaded' : 'unavailable';
      })
      .catch(() => { if (request === behaviorRequest) { behaviorReport = null; behaviorState = 'unavailable'; } })
      .finally(() => { clearTimeout(timer); if (request === behaviorRequest && data) render(); });
  }
  function behaviorEvidence(box) {
    loadBehavior();
    if (!behaviorReport) {
      box.append(el('p', behaviorState === 'loading' ? 'Loading observed behavior…' : 'Behavior evidence unavailable. Existing research and canonical replay evidence remain independent.'));
      return;
    }
    const wallets = behaviorReport.wallets.filter(w => w?.wallet === state.id);
    if (!wallets.length) box.append(el('p', 'No admitted behavior observations for this wallet in the cached sample.'));
    wallets.forEach(w => {
      box.append(el('p', 'In the loaded sample: ' + text(w.buy_count) + ' buys · ' + text(w.sell_count) + ' sells.'),
        el('p', 'Typical trade size: ' + money(w.order_size_usd?.median) + ' — median, estimated by the source.'));
      if (w.sell_count === 0) box.append(el('p', 'No sells in this sample. This does not mean the wallet has never sold.'));
      const details = el('details');
      details.append(el('summary', 'Details · source data and calculations'));
      details.append(el('p', 'Observed buys: ' + text(w.buy_count) + ' · sells: ' + text(w.sell_count) + ' · source: ' + text(w.source) + ' · chain: ' + text(w.chain_id)),
        el('p', 'Median event cadence: ' + text(w.cadence?.median) + ' seconds. Not holding duration or decision frequency.'),
        el('p', 'Median source-estimated order size: ' + money(w.order_size_usd?.median) + ' · priced sample: ' + text(w.order_size_usd?.sample_count) + ' · missing/invalid: ' + text(w.order_size_usd?.missing_or_invalid_count)),
        el('p', 'Observed event IDs: ' + (w.event_ids || []).join(', ')),
        el('pre', text({window: w.window, attribution: w.attribution, buy_token_concentration: w.buy_token_concentration})));
      box.append(details);
    });
    const candidates = behaviorReport.candidates.filter(c => c?.provenance?.wallet === state.id && c.execution === 'not_run');
    if (wallets.length && !candidates.length) box.append(el('p', 'Features only: no candidate passed the three priced buys per token experiment gate.'));
    candidates.forEach(candidate => {
      const p = candidate.provenance, gene = p.mapped_genes?.min_liquidity;
      if (!gene || Object.keys(p.mapped_genes).length !== 1) return;
      const group = el('details');
      group.append(el('summary', candidate.id + ' · wallet-inspired fly candidate · not_run'));
      group.append(entity('token', p.token, 'Inspect candidate token ' + short(p.token)),
        el('p', 'awaiting_matching_market_window · no evaluation or trades run. Not a trained or cloned wallet; no wallet PnL inferred.'),
        el('p', 'Single hypothetical gene vs engine default: min_liquidity: ' + text(behaviorReport.default_genome?.min_liquidity) + ' → ' + text(gene.value)),
        el('p', text(gene.formula) + ' · clipped: ' + text(gene.clipped) + '. Experimental liquidity screen, not an observed wallet preference.'),
        el('p', 'Supporting buy event IDs: ' + (gene.event_ids || []).join(', ')),
        el('pre', text({candidate_id: candidate.id, genome: candidate.genome, default_genes: p.default_genes, evidence_window: p.evidence_window, available_after: p.available_after})),
        el('p', 'All other genes are defaults, not learned behavior. Requires matching token/chain market observations strictly after evidence availability and an unchanged default-genome control.'));
      box.append(group);
    });
  }
  let historyGeneration = 0;
  const histories = new Map();
  function loadHistory(address) {
    if (histories.has(address)) return;
    const entry = {status: 'loading', report: null}, generation = historyGeneration;
    histories.set(address, entry);
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
    root.fetch('/api/wallet-history/' + encodeURIComponent(address), {cache: 'no-store', signal: controller.signal})
      .then(r => r.ok ? r.json() : null)
      .then(r => {
        if (generation !== historyGeneration) return;
        entry.report = r?.wallet === address.toLowerCase() && r?.chain_id === 4663 && Array.isArray(r.groups) ? r : null;
        entry.status = entry.report ? 'loaded' : 'unavailable';
      }).catch(() => { entry.status = 'unavailable'; })
      .finally(() => { clearTimeout(timer); if (generation === historyGeneration && data && state.kind === 'wallet' && state.id === address) dossier(); });
  }
  function historyDetails(box, report) {
    const details = el('details');
    details.append(el('summary', 'Details · per-wallet historical token evidence'),
      el('p', 'Captured ' + date(report.captured_at) + (report.stale ? ' · STALE cached history' : '') + '. ' + text(report.scope?.grouped)),
      el('p', (report.limitations || []).join(' ')));
    Object.entries(report.sources || {}).forEach(([name, url]) => { const safe = safeURL(url); if (safe) { const a = link(name + ' history ↗', safe); a.target = '_blank'; a.rel = 'noopener noreferrer'; details.append(a); } });
    if (report.activity) {
      const activity = el('details'); activity.append(el('summary', 'Dated trade evidence · ' + report.activity.events.length + ' events'), el('p', text(report.activity.scope)), el('p', 'Excluded ' + report.activity.counts.excluded + ' transfer, dust or unclassified rows. Dates: ' + date(report.activity.first_ts) + ' → ' + date(report.activity.last_ts)));
      report.activity.events.forEach(e => activity.append(el('p', date(e.ts) + ' · ' + e.side.toUpperCase() + ' · ' + e.symbol + ' · ' + money(e.usd) + ' · ' + e.token)));
      details.append(activity);
    }
    report.groups.forEach(p => {
      const row = el('details'); row.append(el('summary', p.symbol + ' · ' + p.buys + ' buys / ' + p.sells + ' sells'),
        entity('token', p.token, 'Inspect ' + p.symbol), el('p', 'Source-grouped trades · ' + date(p.first_ts) + ' → ' + date(p.last_ts)),
        el('p', 'Source-reported USD: bought ' + money(p.bought_usd) + ' · sold ' + money(p.sold_usd) + '. Not independently verified wallet funding.'),
        el('p', text(p.transaction_coverage)));
      if (!(p.transactions || []).length) row.append(el('p', 'No individual transaction hashes supplied for this historical group.'));
      (p.transactions || []).forEach(tx => { const url = safeURL(tx.url); if (url) row.append(link(tx.side + ' · ' + tx.classification + ' · ' + short(tx.tx) + ' ↗', url)); });
      details.append(row);
    });
    const native = el('details'); native.append(el('summary', 'Separate native Trenches history · ' + (report.native_history || []).length + ' rows'), el('p', text(report.scope?.native)));
    (report.native_history || []).forEach(p => native.append(el('p', p.symbol + ': ' + p.buys + ' buys / ' + p.sells + ' sells · ' + date(p.opened_ts) + ' → ' + date(p.closed_ts))));
    details.append(native); box.append(details);
  }
  function dossier() {
    const box = $('dossier'); box.replaceChildren(); box.hidden = !state.kind || state.tab === 'method'; if (box.hidden) return;
    const close = el('button', '×', 'close'); close.type = 'button'; close.setAttribute('aria-label', 'Close dossier'); close.onclick = () => { root.location.hash = route(state.tab); $('research-panel').focus(); };
    box.append(close, el('span', state.kind + ' / dossier', 'eyebrow'));
    const record = (state.kind === 'wallet' ? data.wallets : data.tokens).find(row => (state.kind === 'wallet' ? row.address : row.token || row.address) === state.id);
    box.append(el('h2', record?.handle || record?.symbol || record?.name || short(state.id)), el('div', state.id, 'address'));
    if (!record) box.append(el('p', 'No summary row for this address in the snapshot. Related observed fills, if any, remain available below.'));
    const fills = matchingFills(data, state.kind, state.id);
    if (state.kind === 'wallet') {
      const takeaway = el('section', null, 'trader-takeaway');
      takeaway.setAttribute('aria-label', 'Trader takeaway');
      if (record) loadHistory(state.id);
      const history = histories.get(state.id);
      takeaway.append(el('h3', 'Trader takeaway'));
      takeaway.append(el('small', history?.report ? (history.report.activity ? 'Per-wallet dated trades · source-reported' : 'Per-wallet historical groups · source-reported') + (history.report.stale ? ' · STALE cache' : '') : history?.status === 'loading' ? 'Loading per-wallet history… Current sample shown meanwhile.' : 'Per-wallet history unavailable; current sample shown.'));
      takeaway.append(el('p', readableTakeaway(history?.report?.takeaway || traderTakeaway(record, fills, data.tokens, data.window))));
      box.append(takeaway);
      if (history?.report) historyDetails(box, history.report);
    }
    if (record && state.kind === 'wallet') {
      const stats = el('div', null, 'stats'); stats.append(stat('Realized', money(record.realized_pnl, true), signed(record.realized_pnl)), stat('Unrealized', money(record.unrealized_pnl, true), signed(record.unrealized_pnl)), stat('Net PnL', money(record.net_pnl, true), signed(record.net_pnl)), stat('Loaded fills', fills.length)); box.append(stats);
    }
    if (record && state.kind === 'token') {
      const stats = el('div', null, 'stats'); stats.append(stat('Liquidity', money(record.liquidity)), stat('Mark / USD', number(record.mark) === null ? '—' : String(record.mark)), stat('Bought / source', money(record.usd_in)), stat('Sold / source', money(record.usd_out))); box.append(stats);
      if (record.drained || record.honeypot || record.parked) box.append(el('p', 'Source flags: ' + ['drained', 'honeypot', 'parked'].filter(k => record[k]).join(', '), 'negative'));
      const pair = safeURL(record.pair_url); if (pair) { const a = link('View source pair ↗', pair); a.target = '_blank'; a.rel = 'noopener noreferrer'; box.append(a); }
      chart(box, record);
    }
    detailFills(box, fills);
    if (state.kind === 'wallet') {
      const rulesDetails = el('details'); rulesDetails.append(el('summary', 'Details · supported rules'));
      const rules = record ? supportedRules(record, fills) : [];
      if (!rules.length) rulesDetails.append(el('p', 'Insufficient validated history to describe this wallet’s strategy. Loaded fills do not establish position sizing, inventory, intent or a repeatable rule.'));
      rules.forEach(rule => { rulesDetails.append(el('p', rule.description), el('span', 'Supporting fill IDs: ' + rule.fill_ids.join(', '), 'secondary')); });
      box.append(rulesDetails);
    }
    const replayLink = state.kind === 'wallet' ? walletReplayLink(replayEnvelope, state.id) : null;
    const hypothesisLink = state.kind === 'wallet' ? hypothesisReplayLink(hypothesisEnvelope,state.id) : null;
    if (state.kind === 'wallet') {
      const experiment = el('details'); experiment.append(el('summary', 'Details · wallet → experiment'));
      behaviorEvidence(experiment);
      const mappings = (replayEnvelope?.mappings || []).filter(m => m.provenance?.wallet === state.id);
      const admission = el('details'); admission.append(el('summary', 'Details · strict replay admission'));
      admission.append(el('p', replayLink ? 'Admitted founder exists in this completed simulation. Partial mapping, not recovered wallet strategy.' : 'No exact wallet-to-fly mapping established for this wallet. No admitted replay founder. ' + (replayEnvelope?.blocked_reasons || ['Wallet replay unavailable or wallet not admitted.']).join(' ')));
      const evidence = el('details'); evidence.append(el('summary', 'Details · canonical evidence'));
      mappings.forEach(mapping => evidence.append(el('pre', text(mapping))));
      if (replayLink) {
        const founder = replayEnvelope.replay.generations[0].flies.find(f => f.seed_origin?.provenance?.wallet === state.id);
        evidence.append(el('pre', text(founder.seed_origin.provenance)));
      }
      admission.append(evidence); experiment.append(admission); box.append(experiment);
    }
    if (replayLink || hypothesisLink) box.append(el('h3', 'Watch the experiment'));
    if (replayLink) box.append(link('Open strict wallet replay ↗', replayLink, 'colony'));
    if(hypothesisLink){
      const founder=hypothesisEnvelope.replay.generations[0].flies.find(f=>f.seed_origin?.provenance?.wallet===state.id);
      const details=el('details'); details.append(el('summary','Details · experiment evidence'),el('p',text(hypothesisEnvelope.overlap_note||hypothesisEnvelope.overlap||hypothesisEnvelope.temporal_overlap||'')),el('pre',text(founder.seed_origin)));
      box.append(el('p','Historical simulation · exits assumed · not forward validation.'),link('Watch wallet experiment ↗',hypothesisLink,'colony'),details);
    }
    const archive = el('details'); archive.append(el('summary', 'Details · original archive'), el('p', 'Original archive is separate and does not represent this wallet.'), link('Original archive ↗', '/?replay=archive', 'secondary')); box.append(archive);
  }
  function render() {
    doc.querySelectorAll('[data-tab]').forEach(button => { const active = button.dataset.tab === state.tab; button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; });
    $('research-panel').setAttribute('aria-labelledby', 'tab-' + state.tab); $('list-tools').hidden = state.tab === 'method';
    if (!data) return;
    if (state.tab === 'method') method(); else renderList(); dossier();
  }
  async function load() {
    if (!loading) { historyGeneration++; histories.clear(); }
    if (loading) return; loading = true; $('refresh').disabled = true; $('research-panel').setAttribute('aria-busy', 'true'); showStatus(data ? 'Refreshing… Previous snapshot remains visible.' : 'Loading research snapshot…');
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    // Independent optional request: failure must never prevent research rendering.
    const replayController = new AbortController(), replayTimer = setTimeout(() => replayController.abort(), 15000);
    replayEnvelope = null; hypothesisEnvelope = null; const requestId=++replayRequest;
    const hypothesisController=new AbortController(), hypothesisTimer=setTimeout(()=>hypothesisController.abort(),15000);
    root.fetch('/api/hypothesis-replay',{cache:'no-store',signal:hypothesisController.signal})
      .then(response=>response.ok?response.json():null)
      .then(envelope=>{if(requestId!==replayRequest)return;hypothesisEnvelope=envelope;if(data)render();})
      .catch(()=>{if(requestId!==replayRequest)return;hypothesisEnvelope=null;if(data)render();})
      .finally(()=>clearTimeout(hypothesisTimer));
    behaviorRequest++; behaviorReport = null; behaviorState = 'idle';
    root.fetch('/api/wallet-replay', {cache: 'no-store', signal: replayController.signal})
      .then(response => response.ok ? response.json() : null)
      .then(envelope => { if(requestId!==replayRequest)return; replayEnvelope = envelope; if (data) render(); })
      .catch(() => { if(requestId!==replayRequest)return; replayEnvelope = null; if (data) render(); })
      .finally(() => clearTimeout(replayTimer));
    try {
      const response = await root.fetch('/api/research', {headers: {Accept: 'application/json'}, cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw new Error('Research API returned HTTP ' + response.status);
      data = normalize(await response.json()); header(); render(); showStatus('Snapshot loaded · read-only upstream data · select a wallet or token to inspect its evidence.');
    } catch (error) {
      showStatus((data ? 'Refresh failed; previous snapshot retained. ' : 'Research unavailable. ') + (error.name === 'AbortError' ? 'Request timed out.' : error.message) + ' Use Refresh snapshot to retry.', true);
      if (!data) $('results').replaceChildren(el('div', 'No research data loaded. The Colony remains accessible; no demo data is substituted.', 'empty'));
    } finally { clearTimeout(timer); loading = false; $('refresh').disabled = false; $('research-panel').setAttribute('aria-busy', 'false'); }
  }
  $('refresh').onclick = load;
  $('search').oninput = () => { page = 0; render(); }; $('sort').onchange = () => { page = 0; render(); };
  const tabs = [...doc.querySelectorAll('[data-tab]')];
  tabs.forEach((button, i) => { button.onclick = () => { root.location.hash = route(button.dataset.tab); }; button.onkeydown = event => {
    const target = event.key === 'ArrowRight' ? (i + 1) % tabs.length : event.key === 'ArrowLeft' ? (i + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : -1;
    if (target >= 0) { event.preventDefault(); tabs[target].focus(); tabs[target].click(); }
  }; });
  root.addEventListener('hashchange', () => { state = parseHash(root.location.hash); page = 0; render(); if (state.kind && !$('dossier').hidden) $('dossier').focus(); });
  doc.addEventListener('keydown', event => { if (event.key === 'Escape' && state.kind) { root.location.hash = route(state.tab); $('research-panel').focus(); } });
  setInterval(() => { if (data) $('freshness').textContent = freshness(data.as_of); }, 60000);
  render(); load();
})(typeof window !== 'undefined' ? window : globalThis);
