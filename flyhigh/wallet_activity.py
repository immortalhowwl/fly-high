"""Describe dated, source-classified wallet events without reconstructing inventory."""
import math
import re
from collections import defaultdict

ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')

def activity_summary(radar):
    rows = radar.get('fills', [])
    events, seen = [], set()
    for row in rows[:5000]:
        if not isinstance(row, dict):
            continue
        mint = str(row.get('mint', '')).lower()
        ts, usd = row.get('ts'), row.get('usd')
        if (row.get('kind') != 'trade' or row.get('source') != 'rpc'
            or row.get('side') not in ('buy', 'sell') or not ADDRESS.fullmatch(mint)
            or type(ts) not in (int, float) or not math.isfinite(ts) or ts <= 0
            or row.get('priced') == 'no_cash_leg'
            or any(x in str(row.get('flags', '')).lower() for x in ('airdrop', 'transferred', 'not a real'))):
            continue
        # No source event IDs are supplied. Do not deduplicate by timestamp:
        # two fills may genuinely share the same second and amount.
        events.append({'token': mint, 'symbol': str(row.get('sym') or mint[:10])[:60],
                       'ts': ts, 'side': row['side'],
                       'usd': usd if type(usd) in (int, float) and math.isfinite(usd) and usd >= 0 else None,
                       'evidence_kind': 'radar_rpc_trade_classification', 'tx': None})
    events.sort(key=lambda r: (r['ts'], r['token'], r['side']))
    if not events:
        return None
    by_token = defaultdict(list)
    for row in events:
        by_token[row['token']].append(row)
    ordered = sorted(by_token.items(), key=lambda pair: (-sum(e['side']=='buy' for e in pair[1]), pair[0]))
    token, top = ordered[0]
    buys = [e for e in top if e['side']=='buy']
    sells = [e for e in top if e['side']=='sell']
    total_buys = sum(e['side']=='buy' for e in events)
    n = len(events)
    text = f'Observed: the requested 168-hour Robinhood history contains {n} source-classified trade events: {total_buys} buys and {n-total_buys} sells. '
    if len(buys)>1:
        text += f"{top[0]['symbol']} has {len(buys)} buys"
        if all(e['usd'] is not None for e in buys):
            text += f" totaling ${sum(e['usd'] for e in buys):,.2f} in source-reported trade value"
        text += f" and {len(sells)} sells in this window. "
    elif buys:
        text += 'No token has repeated buy events in this sample. '
    else:
        text += 'The sample contains sales but no eligible buys. '
    # Select a simple buy-then-sell sequence independently of returns or dollar value.
    paired = []
    for mint, es in sorted(by_token.items()):
        first_buy = next((e for e in es if e['side']=='buy'), None)
        later_sell = next((e for e in es if first_buy and e['side']=='sell' and e['ts']>first_buy['ts']), None)
        if first_buy and later_sell:
            paired.append((first_buy, later_sell))
    if paired:
        b,s = paired[0]
        text += f"{b['symbol']} shows a buy followed by a sell {(s['ts']-b['ts'])/86400:.1f} days later. "
    if len(buys)>1:
        text += f"Interpretation: repeated entries are visible in {top[0]['symbol']}"
        text += ', alongside sales elsewhere; this is not a uniform buy-and-hold pattern. ' if any(e['side']=='sell' and e['token']!=token for e in events) else ('; the sample also contains sale events. ' if n>total_buys else '; no sale appears in the eligible sample. ')
        text += f"Study: compare the dated {top[0]['symbol']} entries with the sale sequences below. "
    else:
        text += 'Study: trace the dated sales back to earlier purchases before drawing an entry or exit rule. '
    text += 'Trade values are source-reported; event spacing is not a verified holding period or profit. Not Financial Advice.'
    return {'takeaway':text, 'events':events, 'counts':{'source_rows':len(rows),'eligible':n,'excluded':len(rows)-n,'buys':total_buys,'sells':n-total_buys},
            'first_ts':events[0]['ts'],'last_ts':events[-1]['ts'],
            'scope':'Requested 168-hour Robinhood event history, including tokenized stocks; source RPC classification, not independently verified funding. Source provides no event IDs or transaction hashes; rows are not silently deduplicated.'}
