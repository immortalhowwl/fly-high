"""Read-only, keyless Trenches research. Indexer attribution is not chain verification."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = 'https://robinhoodtrenches.com'
DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'research.snapshot.json'
ENDPOINTS = {
    'traders': '/api/traders?window=7d&stocks=false',
    'tape': '/api/tape?limit=500&stocks=false',
    'closed': '/api/closed?window=7d&stocks=false&limit=500',
    'tokens': '/api/tokens?window=7d&stocks=false&limit=100',
    'status': '/api/status',
}
ADDRESS = re.compile(r'^0x[0-9a-fA-F]{40}$')
TX = re.compile(r'^0x[0-9a-fA-F]{64}$')


class TrenchesClient:
    """Five allowlisted GETs, bounded retries/body/timeout and in-process TTL cache."""
    def __init__(self, timeout=10, retries=2, cache_ttl=900):
        self.timeout = max(.1, min(float(timeout), 30))
        self.retries = max(0, min(int(retries), 3))
        self.cache_ttl = max(0, float(cache_ttl))
        self.cache = {}

    def fetch(self, key):
        url = BASE + ENDPOINTS[key]
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < self.cache_ttl:
            return copy.deepcopy(cached[1])
        for attempt in range(self.retries + 1):
            try:
                request = Request(url, headers={'Accept': 'application/json',
                                  'User-Agent': 'FLY-HIGH-Research/1.0 (public read-only research)'})
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read(8 * 1024 * 1024 + 1)
                    if len(body) > 8 * 1024 * 1024:
                        raise ValueError('response exceeds 8 MiB')
                    data = json.loads(body, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
                    expected = dict if key == 'status' else list
                    if not isinstance(data, expected) or (isinstance(data, list) and any(not isinstance(r, dict) for r in data)):
                        raise ValueError('unexpected response schema for ' + key)
                    capture = {'url': url, 'fetched_at': now(), 'http_status': response.status,
                               'sha256': hashlib.sha256(body).hexdigest(),
                               'body': body.decode('utf-8'), 'data': data, 'stale': False}
                self.cache[key] = (time.monotonic(), capture)
                return copy.deepcopy(capture)
            except (OSError, URLError, ValueError) as exc:
                if isinstance(exc, HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                    raise
                if attempt == self.retries:
                    raise
                delay = min(4, .5 * 2 ** attempt)
                if isinstance(exc, HTTPError):
                    try:
                        delay = min(4, max(delay, float(exc.headers.get('Retry-After', 0))))
                    except (ValueError, TypeError):
                        pass
                time.sleep(delay)


def _read_store(path):
    with Path(path).open(encoding='utf-8') as file:
        store = json.load(file)
    if not isinstance(store, dict) or not isinstance(store.get('raw'), dict) or not isinstance(store.get('payload'), dict):
        raise ValueError('invalid research snapshot envelope')
    return store


def _atomic_store(path, store):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(path.parent),
                                         prefix='.' + path.name + '.', suffix='.tmp', delete=False) as file:
            temporary = file.name
            json.dump(store, file, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def load_snapshot(path=None):
    """Return canonical DTO without network access; absent/corrupt cache is explicit."""
    try:
        return _read_store(path or DEFAULT_PATH)['payload']
    except (OSError, ValueError, TypeError) as exc:
        return build_payload({}, ['Snapshot unavailable: ' + str(exc)])


def refresh_snapshot(path=None):
    """Refresh all sources. Failed endpoints retain dated stale captures, never fake rows."""
    path = Path(path or DEFAULT_PATH)
    try:
        old = _read_store(path).get('raw', {})
    except (OSError, ValueError, TypeError):
        old = {}
    raw, warnings = {}, []
    client = TrenchesClient()
    for key in ENDPOINTS:
        try:
            raw[key] = client.fetch(key)
        except (OSError, ValueError) as exc:
            warnings.append(f'{key} refresh failed: {exc}')
            if key in old:
                raw[key] = dict(old[key], stale=True)
                warnings.append(f'{key}: using stale capture from {old[key].get("fetched_at")}.')
    payload = build_payload(raw, warnings)
    _atomic_store(path, {'schema_version': 1, 'refresh_attempted_at': now(),
                         'raw': raw, 'payload': payload})
    return payload


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def address(value):
    return value.lower() if isinstance(value, str) and ADDRESS.fullmatch(value) else None


def number(value):
    return value if type(value) in (float, int) and math.isfinite(value) else None


def build_payload(raw, warnings=None):
    warnings = list(warnings or [])
    warnings.extend([
        'Third-party indexer attribution; wallet/handle identity and receipts are not independently verified by this ingestion.',
        'Latest tape is capped at 500, not a complete 7d ledger; no pagination or backfill.',
        'PnL and win_rate are upstream estimates, not recomputed; open inventory may extend outside 7d.',
        'No inferred trading rules: unknown opening inventory, cash before fills, fees and decision context. No score or execution.',
    ])
    def rows(key):
        return raw.get(key, {}).get('data', [])
    fills, seen = [], set()
    invalid, duplicates = 0, 0
    for row in rows('tape'):
        wallet, token = address(row.get('wallet')), address(row.get('token'))
        identity, ts, tx = row.get('id'), row.get('ts'), row.get('tx')
        if (type(identity) is not int or type(ts) is not int or ts <= 0 or not wallet or not token
                or not isinstance(tx, str) or not TX.fullmatch(tx) or row.get('side') not in ('buy', 'sell')):
            invalid += 1
            continue
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        fill = {k: row.get(k) for k in ('id', 'ts', 'tx', 'side', 'symbol')}
        fill.update(wallet=wallet, token=token, usd=number(row.get('usd')),
                    amount=number(row.get('amount')), chain_id=4663,
                    source='robinhoodtrenches', provenance='indexer_reported_not_receipt_verified')
        # Keep provenance signals; never substitute payer/profile address for wallet.
        for key in ('handle', 'block', 'funding', 'priced', 'flags', 'two_sided', 'is_stock', 'quote_token'):
            if key in row:
                fill[key] = row[key]
        fills.append(fill)
    fills.sort(key=lambda row: (row['ts'], row['id']))
    wallets = []
    for row in rows('traders'):
        wallet = address(row.get('address'))
        if wallet is None:
            invalid += 1
            continue
        item = dict(row)
        # Do not carry an unlabelled upstream score into the canonical contract.
        item.pop('score', None)
        item.update(address=wallet, chain_id=4663, identity_source='robinhoodtrenches',
                    identity_verified=False)
        for key in ('realized_pnl', 'unrealized_pnl', 'net_pnl', 'fills', 'win_rate'):
            item[key] = number(row.get(key))
        item.setdefault('handle', None)
        item['rules'] = {'status': 'insufficient_history', 'mapped_genes': {},
                         'reason': 'No cash/fees/opening inventory; bounded indexer tape cannot recover strategy.'}
        # Current strict wallet_rules boundary requires verified quote units and observed
        # execution. USD valuation is not proof of quote asset: never fabricate inputs.
        try:
            from .wallet_rules import analyze_fills
            report = analyze_fills([], opening_inventory_known_zero=False)
            item['rules']['analysis'] = report
            item['rules']['method'] = 'wallet_rules.analyze_fills; no admissible execution history'
        except (ImportError, AttributeError):
            item['rules']['method'] = 'wallet_rules unavailable; no inference'
        item['rules']['indexer_fill_count'] = sum(f['wallet'] == wallet for f in fills)
        wallets.append(item)
    tokens = []
    for row in rows('tokens'):
        token = address(row.get('token'))
        if token:
            tokens.append(dict(row, token=token))
        else:
            invalid += 1
    timestamps = [f['ts'] for f in fills]
    fetch_times = [v['fetched_at'] for v in raw.values() if v.get('fetched_at')]
    if invalid:
        warnings.append(f'{invalid} malformed rows omitted from canonical data; preserved in raw captures.')
    return {
        'as_of': max(fetch_times) if fetch_times else None,
        'source': {'name': 'Robinhood Trenches', 'url': BASE, 'chain_id': 4663,
                   'attribution': 'Third-party public indexer', 'receipt_verified': False},
        'window': '7d',
        'coverage': {'stocks': False, 'complete_history': False, 'tape_limit': 500,
                     'closed_limit': 500, 'token_limit': 100,
                     'since': min(timestamps) if timestamps else None,
                     'until': max(timestamps) if timestamps else None,
                     'tape_window': 'latest available (not guaranteed 7d)',
                     'endpoints': {key: {k: value.get(k) for k in ('url', 'fetched_at', 'http_status', 'stale')}
                                   for key, value in raw.items()},
                     'missing_endpoints': [key for key in ENDPOINTS if key not in raw]},
        'wallets': wallets, 'fills': fills, 'tokens': tokens,
        'metrics': {'wallet_count': len(wallets), 'fill_count': len(fills),
                    'token_count': len(tokens), 'closed_count': len(rows('closed')),
                    'unpriced_fill_count': sum(f['usd'] is None for f in fills),
                    'duplicate_fill_count': duplicates, 'invalid_row_count': invalid,
                    'indexer_status': raw.get('status', {}).get('data'),
                    'inferred_rule_count': 0},
        'warnings': warnings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Fetch public GET endpoints and atomically save')
    parser.add_argument('--path', type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    payload = refresh_snapshot(args.path) if args.refresh else load_snapshot(args.path)
    print(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    return 1 if payload['coverage']['missing_endpoints'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
