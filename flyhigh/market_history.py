"""Read-only COPY OHLCV. Canonical timestamp is CLOSED time, not import_history input."""
import math
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCE = dict(symbol='COPY', chain='robinhood',
    token='0xac79255f6f404eba14f316e8669d76573a2d7b1e',
    pool='0x827534609c9f74fc7d950b91e268d22419611e8a1d7a557dec6716cba11ee605')
DEFAULT_DIR = Path(__file__).resolve().parents[1] / 'data' / 'market-history'
BASE = 'https://api.geckoterminal.com/api/v2/networks/' + SOURCE['chain'] + '/pools/' + SOURCE['pool']


def fetch_json(url):
    """At most two GETs per refresh; 20s timeout and 2 MiB response limit each."""
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urlopen(req, timeout=20) as response:
        if response.geturl() != url:
            raise ValueError('unexpected source redirect')
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError('response exceeds limit')
    return raw


def _utc(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def refresh(directory=DEFAULT_DIR, *, window_count=250, as_of=None, fetch=fetch_json):
    """Fixed latest-N observed candles, chosen BEFORE fetch; no backfill or ranking.

    Returns canonical close-time bars. Never pass these bars to import_history.adapt,
    which expects open-time input. Historical liquidity is deliberately absent.
    """
    if type(window_count) is not int or not 1 <= window_count <= 1000:
        raise ValueError('window_count must be 1..1000')
    started = time.time()
    cutoff = started if as_of is None else as_of
    if not math.isfinite(cutoff) or cutoff > started or cutoff < 0:
        raise ValueError('as_of must not be in the future')
    url = BASE + '/ohlcv/minute?' + urlencode(dict(aggregate=5, limit=window_count,
        currency='usd', token=SOURCE['token'], include_empty_intervals='false', before_timestamp=int(cutoff)))
    pool_raw = fetch(BASE)
    pool = json.loads(pool_raw)['data']
    if (pool['id'] != SOURCE['chain']+'_'+SOURCE['pool'] or
        pool['attributes']['address'] != SOURCE['pool'] or
        pool['relationships']['base_token']['data']['id'] != SOURCE['chain']+'_'+SOURCE['token']):
        raise ValueError('chain/pool/base token identity mismatch')
    raw = fetch(url)
    payload = json.loads(raw)
    if payload['meta']['base']['address'] != SOURCE['token']:
        raise ValueError('OHLCV base token mismatch')
    rows = payload['data']['attributes']['ohlcv_list']
    if len(rows) > window_count:
        raise ValueError('provider exceeded fixed window')
    bars = canonicalize(rows, as_of=cutoff)
    if not bars:
        raise ValueError('no closed candles; previous snapshot preserved')
    directory = Path(directory)
    rawdir = directory / 'raw'
    rawdir.mkdir(parents=True, exist_ok=True)
    receipts = []
    for label, body, source_url in [('pool', pool_raw, BASE), ('ohlcv', raw, url)]:
        digest = hashlib.sha256(body).hexdigest()
        relative = 'raw/' + label + '-' + digest + '.json'
        (directory / relative).write_bytes(body)
        receipts.append(dict(file=relative, sha256=digest, source_url=source_url))
    doc = dict(schema_version=1, mode='observed_market_history', provider='GeckoTerminal public API',
        **SOURCE, interval_seconds=300, timestamp_semantics='closed', timestamp_unit='unix_seconds',
        price_currency='usd', collected_at=_utc(time.time()), as_of=cutoff,
        source_url=url, raw_sources=receipts,
        window=dict(requested_count=window_count, rule='latest N provider nonempty candles before fixed as_of; incomplete excluded; no refill'),
        methodology=dict(historical_liquidity=False, interpolated=False, max_gap=300,
            warning='Observed prices only. Not seeded replay; no fills or profitability claims.'),
        quality=dict(raw_count=len(rows), closed_count=len(bars),
            gaps_over_300_seconds=sum(b['timestamp']-a['timestamp'] > 300 for a,b in zip(bars,bars[1:])),
            excluded_incomplete=sum(row[0]+300 > cutoff for row in rows)), bars=bars)
    temp = directory / 'copy.latest.json.tmp'
    temp.write_text(json.dumps(doc, indent=2, allow_nan=False)+'\n')
    temp.replace(directory / 'copy.latest.json')
    return doc


def load(directory=DEFAULT_DIR, *, as_of=None, verify_raw=True):
    """Load verified canonical closed candles, optionally restricted to event time.

    Collection itself is retrospective: forward consumers must also enforce their
    own start/evidence cutoff; this API does not attest historical availability.
    """
    directory = Path(directory)
    doc = json.loads((directory / 'copy.latest.json').read_text())
    if any(doc.get(k) != v for k,v in SOURCE.items()) or doc.get('timestamp_semantics') != 'closed' or doc.get('interval_seconds') != 300:
        raise ValueError('canonical identity or timestamp semantics mismatch')
    for receipt in doc['raw_sources'] if verify_raw else []:
        path = (directory / receipt['file']).resolve()
        if not path.is_relative_to((directory / 'raw').resolve()):
            raise ValueError('invalid receipt path')
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt['sha256']:
            raise ValueError('raw receipt checksum mismatch')
    cutoff = min(time.time(), doc['as_of'], as_of if as_of is not None else doc['as_of'])
    if not math.isfinite(cutoff):
        raise ValueError('invalid as_of')
    rows = []
    for b in doc['bars']:
        if b['timestamp'] != b['open_timestamp'] + INTERVAL:
            raise ValueError('double shifted or invalid close timestamp')
        rows.append([b['open_timestamp'], b['open'], b['high'], b['low'], b['close'], b['volume']])
    doc['bars'] = canonicalize(rows, as_of=cutoff)
    doc['view_as_of'] = cutoff
    doc['view_count'] = len(doc['bars'])
    return doc

INTERVAL = 300


def canonicalize(rows, *, as_of):
    """Validate all rows, collapse identical duplicates, retain missing intervals."""
    if not math.isfinite(as_of):
        raise ValueError('invalid as_of')
    found = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            raise ValueError('expected six OHLCV fields')
        if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in row):
            raise ValueError('nonfinite or nonnumeric OHLCV')
        t, o, h, l, c, v = row
        if t < 0 or t != int(t) or t % INTERVAL or min(o,h,l,c) <= 0 or v < 0 or not l <= min(o,c) <= max(o,c) <= h:
            raise ValueError('invalid OHLCV bounds or timestamp')
        bar = dict(timestamp=int(t)+INTERVAL, open_timestamp=int(t), open=o, high=h, low=l, close=c, volume=v)
        if t in found and found[t] != bar:
            raise ValueError('conflicting duplicate candle')
        found[t] = bar
    return [found[t] for t in sorted(found) if t + INTERVAL <= as_of]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['refresh', 'load'])
    parser.add_argument('--directory', default=str(DEFAULT_DIR))
    parser.add_argument('--window-count', type=int, default=250)
    args = parser.parse_args()
    if args.action == 'refresh':
        refresh(args.directory, window_count=args.window_count)
    doc = load(args.directory)
    bars = doc['bars']
    print(json.dumps(dict(path=str(Path(args.directory)/'copy.latest.json'),
        count=len(bars), first_close=_utc(bars[0]['timestamp']) if bars else None,
        last_close=_utc(bars[-1]['timestamp']) if bars else None,
        quality=doc['quality'], window=doc['window']), indent=2))


if __name__ == '__main__':
    main()
