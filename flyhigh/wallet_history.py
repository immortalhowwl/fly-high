"""Bounded, cached per-known-wallet history. Descriptive only; no replay inputs.

Trenches' native trader route has bags/history, but no individual fills. Radar's
book supplies historical grouped buys/sells (analyze.py _book/_own), independently
of its hours-limited fill list. Never consume generated summaries or PnL.
"""
import copy
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

ADDRESS = re.compile(r'0x[0-9a-fA-F]{40}\Z')
TX = re.compile(r'0x[0-9a-fA-F]{64}\Z')
MAX_BYTES = 4_000_000

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('history source redirect rejected')

def fetch_json(url):
    with build_opener(NoRedirect).open(Request(url, headers={'User-Agent': 'FLY-HIGH/1.0 wallet research', 'Accept': 'application/json'}), timeout=6) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError('oversized history response')
    return json.loads(body)

def number(v):
    return v if type(v) in (int, float) and math.isfinite(v) and v >= 0 else None

def excluded(row):
    flags = str(row.get('flags', '')).lower()
    return row.get('priced') == 'no_cash_leg' or any(x in flags for x in ('airdrop', 'not a real buy', 'transferred')) or row.get('kind', 'trade') != 'trade'

def build_history(wallet, radar, native=None, *, captured_at=None, recent_fills=()):
    address = wallet['address'].lower()
    if not isinstance(radar, dict) or str(radar.get('address', '')).lower() != address or radar.get('chain') != 'robinhood':
        raise ValueError('history wallet/chain mismatch')
    captured_at = captured_at or time.time()
    groups, rejected, seen = [], 0, set()
    for p in (radar.get('positions', []) + radar.get('closed', []))[:1000]:
        token = str(p.get('token', '')).lower()
        if p.get('chain') != 'robinhood' or not ADDRESS.fullmatch(token) or excluded(p):
            rejected += 1
            continue
        buys, sells = p.get('buys'), p.get('sells')
        if type(buys) is not int or type(sells) is not int or min(buys, sells) < 0 or buys + sells == 0 or token in seen:
            continue
        seen.add(token)
        refs = []
        for f in recent_fills:
            if str(f.get('wallet', '')).lower() == address and str(f.get('token', '')).lower() == token and TX.fullmatch(str(f.get('tx', ''))):
                refs.append({'id': f.get('id'), 'ts': f.get('ts'), 'side': f.get('side'), 'tx': f['tx'], 'classification': 'excluded_transfer_or_no_cash_leg' if excluded(f) else 'source_reported_trade', 'url': 'https://robinhoodchain.blockscout.com/tx/' + f['tx']})
        groups.append({'token': token, 'symbol': str(p.get('sym') or token[:10])[:80], 'chain_id': 4663,
                       'buys': buys, 'sells': sells, 'bought_usd': number(p.get('bought_usd')), 'sold_usd': number(p.get('sold_usd')),
                       'first_ts': number(p.get('first_ts')), 'last_ts': number(p.get('last_ts')),
                       'source_read_at': number(p.get('read_at')), 'evidence_kind': 'source_grouped_historical_trades',
                       'amount_basis': 'Radar source-reported trade USD; not independently verified wallet funding',
                       'transactions': refs, 'transaction_coverage': 'References from separate recent Trenches tape, not a reconstruction of grouped totals'})
    groups.sort(key=lambda p: (-p['buys'], -p['sells'], p['token']))
    top = groups[:2]
    observations = '; '.join(f"{p['symbol']}: {p['buys']} buys and {p['sells']} sells" for p in top)
    if top:
        interpretation = ('Repeated entries coexist with selling in ' + next(p['symbol'] for p in top if p['buys'] > 1 and p['sells'] > 0) + '; this is not a one-buy-only pattern.' if any(p['buys'] > 1 and p['sells'] > 0 for p in top) else 'These are token-specific entry/exit counts, not a recovered strategy.')
        study = ('Compare the individual entry and sell transactions in ' + top[0]['symbol'] + ' before testing an entry/exit hypothesis; grouped totals cannot reveal order sequence, holding time or a full exit.')
        takeaway = f'Observed — Robinhood historical grouped trades reported by Radar: {observations}. Interpretation — {interpretation} Study — {study} Not Financial Advice.'
    else:
        takeaway = None
    native_history = []
    if native is not None:
        if not isinstance(native, dict) or str(native.get('address', '')).lower() != address:
            raise ValueError('native history wallet mismatch')
        for p in native.get('history', [])[:500]:
            if ADDRESS.fullmatch(str(p.get('token', ''))) and not p.get('is_stock'):
                native_history.append({k: p.get(k) for k in ('token', 'symbol', 'opened_ts', 'closed_ts', 'buys', 'sells')})
    from .wallet_activity import activity_summary
    activity = activity_summary(radar)
    return {'schema_version': 1, 'status': 'available' if groups or activity else 'insufficient_history', 'wallet': address, 'chain_id': 4663,
            'captured_at': captured_at, 'stale': False, 'takeaway': activity['takeaway'] if activity else takeaway, 'groups': groups, 'activity': activity,
            'sources': {'radar': f'https://fomoradar.app/api/trader/{quote(address)}?hours=168',
                        'native': f'https://rhtrenches.com/api/trader/{quote(str(wallet.get("handle") or address), safe="")}?window=7d&stocks=false'},
            'scope': {'grouped': 'Historical book, NOT restricted to requested 168 hours; completeness unknown', 'recent_fills_requested_hours': 168,
                      'source_tape_from': radar.get('tape_from'), 'source_fill_count': len(radar.get('fills', [])),
                      'excluded_recent_fill_count': sum(excluded(f) for f in radar.get('fills', [])),
                      'rejected_group_count': rejected, 'native': 'Separate native 7d request; history may be broader; not added to Radar counts'},
            'native_history': native_history,
            'limitations': ['Grouped counts are source-supported, not independently receipt-verified; legacy unclassified trades may remain in the source.',
                            'Source USD is not proof of personal cash spent. Missing tx hashes stay missing. No PnL, full-exit or holding-time inference.']}

class WalletHistory:
    def __init__(self, fetch=fetch_json, ttl=300):
        self.fetch, self.ttl = fetch, ttl
        self.cache, self.locks = {}, {}
        self.lock = threading.Lock()

    def get(self, address, snapshot):
        if not ADDRESS.fullmatch(address):
            raise KeyError('unknown wallet')
        address = address.lower()
        wallet = next((w for w in snapshot.get('wallets', []) if str(w.get('address', '')).lower() == address), None)
        if wallet is None:
            raise KeyError('unknown wallet')
        with self.lock:
            lock = self.locks.setdefault(address, threading.Lock())
        with lock:
            cached = self.cache.get(address)
            if cached and time.monotonic() - cached[0] < self.ttl:
                return copy.deepcopy(cached[1])
            radar_url = f'https://fomoradar.app/api/trader/{address}?hours=168'
            native_url = f'https://rhtrenches.com/api/trader/{quote(str(wallet.get("handle") or address), safe="")}?window=7d&stocks=false'
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    rf, nf = pool.submit(self.fetch, radar_url), pool.submit(self.fetch, native_url)
                    radar = rf.result()
                    try: native = nf.result()
                    except Exception: native = None
                result = build_history(wallet, radar, native, recent_fills=snapshot.get('fills', []))
                result['native_status'] = 'available' if native is not None else 'unavailable'
                self.cache[address] = (time.monotonic(), result)
                return copy.deepcopy(result)
            except Exception:
                if cached:
                    result = copy.deepcopy(cached[1]); result['stale'] = True
                    return result
                raise ValueError('Wallet history temporarily unavailable') from None
