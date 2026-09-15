"""Three read-only observation rules over the canonical, bounded source tape.

No acquisition, arbitrary wallet input, score, replay or execution. Per-wallet
historical books are deliberately not merged into this common event window.
"""
from collections import defaultdict
from .wallet_history import ADDRESS, TX, excluded, number


def build_observations(snapshot):
    coverage = snapshot.get('coverage', {})
    since, until = number(coverage.get('since')), number(coverage.get('until'))
    wallets = {}
    for row in snapshot.get('wallets', []):
        address = str(row.get('address', '')).lower()
        if ADDRESS.fullmatch(address):
            wallets.setdefault(address, {'address': address, 'handle': str(row.get('handle') or address)[:100]})
    rows = snapshot.get('fills', [])
    events, seen = [], set()
    for row in rows:
        wallet, token = str(row.get('wallet', '')).lower(), str(row.get('token', '')).lower()
        ts = number(row.get('ts'))
        source_id = row.get('id')
        if (wallet not in wallets or not ADDRESS.fullmatch(token)
            or row.get('chain_id') != 4663 or row.get('source') != 'robinhoodtrenches'
            or row.get('side') not in ('buy', 'sell') or excluded(row)
            or row.get('priced') != 'cash_leg' or source_id is None
            or ts is None or ts <= 0 or since is None or until is None or not since <= ts <= until):
            continue
        # Stable indexer event IDs, never transaction-only or wallet/token dedupe.
        event_id = str(source_id)
        if event_id in seen:
            continue
        seen.add(event_id)
        tx = str(row.get('tx', ''))
        events.append({'id': event_id, 'wallet': wallet, 'handle': wallets[wallet]['handle'],
                       'token': token, 'symbol': str(row.get('symbol') or token[:10])[:80],
                       'side': row['side'], 'ts': ts, 'usd': number(row.get('usd')),
                       'flags': row.get('flags', []),
                       'transaction_url': 'https://robinhoodchain.blockscout.com/tx/' + tx if TX.fullmatch(tx) else None,
                       'evidence_kind': 'indexer_cash_leg_trade_not_receipt_verified'})
    events.sort(key=lambda e: (-e['ts'], e['id']))
    buys = defaultdict(list)
    for event in events:
        if event['side'] == 'buy':
            buys[event['token']].append(event)
    groups = []
    for token, token_events in buys.items():
        distinct = sorted({e['wallet'] for e in token_events})
        if len(distinct) >= 2:
            groups.append({'token': token, 'symbol': token_events[0]['symbol'], 'wallets': distinct,
                           'event_ids': [e['id'] for e in token_events],
                           'last_ts': max(e['ts'] for e in token_events)})
    groups.sort(key=lambda g: (-g['last_ts'], g['token']))
    exits = [e for e in events if e['side'] == 'sell']
    for wallet in wallets.values():
        own = [e for e in events if e['wallet'] == wallet['address']]
        wallet['events'] = len(own)
        wallet['last_ts'] = max((e['ts'] for e in own), default=None)
    tape = coverage.get('endpoints', {}).get('tape', {})
    return {'schema_version': 1, 'status': 'available' if events else 'empty',
            'execution_enabled': False, 'chain_id': 4663, 'as_of': snapshot.get('as_of'),
            'source': {'name': 'Robinhood Trenches', 'captured_at': tape.get('fetched_at'),
                       'stale': bool(tape.get('stale', True)),
                       'url': 'https://robinhoodtrenches.com/api/tape?limit=500&stocks=false'},
            'window': {'since': since, 'until': until, 'label': 'Bounded source tape; not a complete 7-day history'},
            'roster': list(wallets.values()), 'events': events, 'groups': groups, 'exits': exits,
            'counts': {'roster': len(wallets), 'source_rows': len(rows), 'events': len(events),
                       'excluded_or_duplicate': len(rows)-len(events),
                       'buys': len(events)-len(exits), 'sells': len(exits), 'groups': len(groups)},
            'rules': {'trader': 'Buys and sells by the selected known wallet in this source window.',
                      'group': 'A token bought by at least 2 distinct tracked wallets in this source window; repeat buys by one wallet count once toward the threshold.',
                      'exits': 'Sell events by the same tracked roster in this source window; a sale does not establish a full exit.'},
            'limits': 'Source-reported cash-leg trades, not independently verified funding or wallet identity. Airdrops, transfers, no-cash-leg and invalid rows excluded. No positions, returns or execution inferred.'}
