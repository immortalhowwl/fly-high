"""Explicit RETROSPECTIVE wallet hypotheses on identity-checked historical prices.

Not the causal seed_candidates export and not wallet_replay. No live execution.
Raw HTTP receipts are embedded in the saved report so it is independently reusable.
"""
import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.parse import urlencode

from .behavior_candidates import build_behavior_candidates
from .engine import Genome, SeedGenome, evolve, simulate
from .market_history import fetch_json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/hypothesis-replay.report.json'
NETWORK = 'robinhood'
CHAIN_ID = 4663
KIND = 'retrospective_wallet_inspired_hypothesis'
LIMITS = [
    'RETROSPECTIVE hypothesis simulation, not a causal forward test or recovered trader strategy.',
    'Wallet evidence may overlap BOTH engine partitions. The field holdout is a legacy API name, NOT unseen evidence.',
    'Historical USD prices are observed; constant liquidity, fills, fees and slippage are assumed.',
    'Source-estimated USD order scale is not wallet allocation, settlement amount or intent.',
    'No claim of wallet PnL, executable exits, profitable generalization or recommendation.',
    'A source honeypot flag or zero observed sells invalidates executable-profit interpretation; simulated sells do not prove sellability.',
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def select_experiment(snapshot):
    """Selection depends only on observed buy counts, never market performance."""
    behavior = build_behavior_candidates(snapshot)
    eligible = {c['provenance']['token'] for c in behavior['candidates']
                if c['provenance']['chain_id'] == CHAIN_ID}
    counts = Counter(e['token'] for w in behavior['wallets'] if w['chain_id'] == CHAIN_ID
                     for e in w['events'] if e['side'] == 'buy' and e['token'] in eligible)
    if not counts:
        raise ValueError('no wallet hypotheses on supported chain 4663')
    token = sorted(counts, key=lambda t: (-counts[t], t))[0]
    return behavior, dict(token=token, chain=NETWORK, chain_id=CHAIN_ID,
        observed_buy_count=counts[token], interval_seconds=60, requested_count=1000,
        rule='most observed buys among eligible tokens on chain 4663; lexical tie break; latest 1000 nonempty 1-minute closed candles before fixed capture cutoff; no refill or alternative token after results',
        assumed_execution_liquidity_usd=30000, seed=17, population=24, generations=6)


def capture_market(selection, *, fetch=fetch_json, as_of=None):
    cutoff = int(time.time()) if as_of is None else as_of
    if type(cutoff) is not int or not 0 < cutoff <= time.time():
        raise ValueError('invalid fixed cutoff')
    token = selection['token']
    base = f'https://api.geckoterminal.com/api/v2/networks/{NETWORK}'
    receipts = []
    def get(url):
        raw = fetch(url)
        receipts.append(dict(url=url, captured_at=datetime.now(timezone.utc).isoformat(),
                             sha256=hashlib.sha256(raw).hexdigest(), raw_body=raw.decode()))
        return json.loads(raw)
    pools = get(f'{base}/tokens/{token}/pools')['data']
    matching = [p for p in pools if p['relationships']['base_token']['data']['id'] == NETWORK+'_'+token]
    if not matching:
        raise ValueError('no matching base-token pool; quote reversal not supported')
    # Address order is fixed and does not rank returns, liquidity or later results.
    pool = sorted(matching, key=lambda p: p['attributes']['address'])[0]['attributes']['address']
    params = urlencode(dict(aggregate=1, limit=1000, currency='usd', token=token,
                           include_empty_intervals='false', before_timestamp=cutoff))
    get(f'{base}/pools/{pool}/ohlcv/minute?{params}')
    market = dict(token=token, chain=NETWORK, chain_id=CHAIN_ID, pool=pool,
                  as_of=cutoff, interval_seconds=60, timestamp_semantics='closed',
                  raw_sources=receipts)
    verified_bars(market, selection)
    return market


def verified_bars(market, selection):
    """Reconstruct bars from receipts, not caller-supplied labeled prices."""
    from urllib.parse import urlparse, parse_qs
    if (market['token'] != selection['token'] or market['chain'] != NETWORK
            or market['chain_id'] != CHAIN_ID or market['interval_seconds'] != 60
            or market['timestamp_semantics'] != 'closed'):
        raise ValueError('market chain/token/timestamp mismatch')
    token, pool = market['token'], market['pool']
    prefix = f'https://api.geckoterminal.com/api/v2/networks/{NETWORK}'
    sources = market['raw_sources']
    if len(sources) != 2 or sources[0]['url'] != f'{prefix}/tokens/{token}/pools':
        raise ValueError('missing identity receipt')
    bodies = []
    for receipt in sources:
        if hashlib.sha256(receipt['raw_body'].encode()).hexdigest() != receipt['sha256']:
            raise ValueError('raw receipt digest mismatch')
        bodies.append(json.loads(receipt['raw_body']))
    matches = [p for p in bodies[0]['data'] if p['attributes']['address'] == pool]
    if len(matches) != 1 or matches[0]['id'] != NETWORK+'_'+pool or matches[0]['relationships']['base_token']['data']['id'] != NETWORK+'_'+token:
        raise ValueError('pool/base identity mismatch')
    parsed = urlparse(sources[1]['url'])
    expected = urlparse(f'{prefix}/pools/{pool}/ohlcv/minute')
    if (parsed.scheme, parsed.netloc, parsed.path) != (expected.scheme, expected.netloc, expected.path):
        raise ValueError('candle URL identity mismatch')
    q = parse_qs(parsed.query)
    for key, val in dict(aggregate='1',limit='1000',currency='usd',token=token,
                        include_empty_intervals='false',before_timestamp=str(market['as_of'])).items():
        if q.get(key) != [val]:
            raise ValueError('candle query mismatch: '+key)
    payload = bodies[1]
    if payload['meta']['base']['address'] != token:
        raise ValueError('candle token metadata mismatch')
    rows = payload['data']['attributes']['ohlcv_list']
    if len(rows) > 1000:
        raise ValueError('provider exceeded fixed window')
    found = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 6 or any(type(v) not in (int,float) or not math.isfinite(v) for v in row):
            raise ValueError('invalid OHLCV numeric fields')
        t,o,h,l,c,v = row
        if t <= 0 or t != int(t) or t % 60 or min(o,h,l,c) <= 0 or v < 0 or not l <= min(o,c) <= max(o,c) <= h:
            raise ValueError('invalid OHLCV bounds')
        if t in found and found[t] != row:
            raise ValueError('conflicting duplicate candle')
        found[t] = row
    if type(market['as_of']) is not int or not 0 < market['as_of'] <= time.time():
        raise ValueError('invalid close cutoff')
    return [dict(timestamp=int(t)+60, price=found[t][4],
                 liquidity=selection['assumed_execution_liquidity_usd'])
            for t in sorted(found) if t+60 <= market['as_of']]


def build_replay(snapshot, market=None, *, fetch=fetch_json):
    behavior, selection = select_experiment(snapshot)
    market = capture_market(selection, fetch=fetch) if market is None else market
    bars = verified_bars(market, selection)
    if len(bars) < 80:
        raise ValueError(f'selected token has {len(bars)} closed bars; engine requires 80; no replacement token/window')
    candidates = [c for c in behavior['candidates'] if c['provenance']['token'] == selection['token']
                  and c['provenance']['chain_id'] == CHAIN_ID][:selection['population']-1]
    seeds = []
    for c in candidates:
        provenance = deepcopy(c['provenance'])
        provenance.update(kind=KIND, label='RETROSPECTIVE wallet-inspired hypothesis',
            candidate_id=c['id'], original_kind=provenance['kind'], causal_forward_test=False,
            evidence_may_overlap_evaluation=True, evaluation_scope='retrospective comparison only')
        seeds.append(SeedGenome(Genome(**c['genome']), provenance))
    if not seeds:
        raise ValueError('no matching wallet seed; refuse unseeded fallback')
    # Default founder shares the same exact bars, costs, depth and evolution schedule.
    seeds.append(SeedGenome(Genome(), dict(kind='retrospective_default_control', label='Default Genome control; not wallet-derived')))
    replay = evolve(bars, seed=selection['seed'], population=selection['population'],
                    generations=selection['generations'], max_gap=60, seed_genomes=seeds)
    token_info = next((t for t in snapshot.get('payload',snapshot).get('tokens',[]) if t['token']==selection['token']), {})
    replay.update(mode='historical_prices_assumed_liquidity', experiment_kind=KIND,
                  source=dict(symbol=token_info.get('symbol'), token=selection['token'], chain=NETWORK,
                              chain_id=CHAIN_ID, pool=market['pool'], provider='GeckoTerminal public API',
                              url=market['raw_sources'][1]['url'], sha256=market['raw_sources'][1]['sha256']))
    replay['methodology'].update(historical_liquidity=False, assumed_execution_liquidity_usd=30000,
        timestamp_semantics='closed', interpolated=False, causal_forward_test=False,
        holdout='Legacy field: last 30% retrospective price partition; NOT unseen wallet evidence or causal forward evaluation',
        warnings=LIMITS)
    split = replay['split']
    control = dict(genome=asdict(Genome()), train=simulate(Genome(),bars[:split],max_gap=60),
                   retrospective_tail=simulate(Genome(),bars[split:],max_gap=60))
    origins = {}
    for generation in replay['generations']:
        for fly in generation['flies']:
            if fly['id'] in origins:
                continue
            p = fly.get('seed_origin',{}).get('provenance',{})
            roots = [fly['id']] if p.get('kind') == KIND else []
            for parent in fly['parents']:
                roots.extend(origins.get(parent,[]))
            origins[fly['id']] = sorted(set(roots))
    founders = [f['id'] for f in replay['generations'][0]['flies'] if f.get('seed_origin',{}).get('provenance',{}).get('kind') == KIND]
    wallets = sorted({c['provenance']['wallet'] for c in candidates})
    unique_flies = {}
    for generation in replay['generations']:
        for fly in generation['flies']:
            unique_flies.setdefault(fly['id'], fly)
    linked_descendants = [f for f in unique_flies.values() if f['parents'] and origins[f['id']]]
    # First trading descendant in birth order, NOT best-return showcase selection.
    example = next((f for f in linked_descendants if f['result']['trades']), None)
    summary = dict(wallet_count=len(wallets), founder_count=len(founders),
        unique_founder_genomes=len({digest(c['genome']) for c in candidates}),
        evaluated_fly_count=len(unique_flies), wallet_descendant_count=len(linked_descendants),
        wallet_descendant_fills=sum(len(f['result']['trades']) for f in linked_descendants),
        founder_fills=sum(len(unique_flies[f]['result']['trades']) for f in founders),
        example_fly_id=example['id'] if example else (founders[0] if founders else None),
        example_rule='first wallet-linked descendant with simulated fills in birth order; not highest return',
        champion_wallet_roots=origins[replay['champion']['id']],
        interpretation='Repeated identical founders retain distinct wallet attribution, not independent strategy evidence. Default-control and random lineages are not wallet-derived. Model depth may prevent every unmutated wallet hypothesis from trading.')
    report = dict(schema_version=1, status='completed', execution='simulated', experiment_kind=KIND,
        label='RETROSPECTIVE wallet-inspired experiment', seed_count=len(candidates), blocked_reasons=[],
        selection=selection, summary=summary, market=market, inputs=dict(research_sha256=digest(snapshot)),
        evidence=dict(wallets=[w for w in behavior['wallets'] if w['wallet'] in wallets], candidates=candidates,
                      token_source_flags={k:token_info.get(k) for k in ('honeypot','drained','buys24','sells24')}),
        quality=dict(closed_bars=len(bars), first_close=bars[0]['timestamp'], last_close=bars[-1]['timestamp'],
                     gaps_over_interval=sum(b['timestamp']-a['timestamp']>60 for a,b in zip(bars,bars[1:]))),
        lineage=dict(founder_ids=founders, wallet_roots_by_fly=origins), control=control,
        limits=LIMITS, replay=replay)
    json.dumps(report, allow_nan=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=ROOT/'data/research.snapshot.json')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--reuse-market', type=Path, help='Use and reverify embedded market receipts from a previous report')
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text())
        market = json.loads(args.reuse_market.read_text())['market'] if args.reuse_market else None
        report = build_replay(snapshot, market)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        report = dict(schema_version=1,status='blocked',execution='not_run',seed_count=0,
                      blocked_reasons=[str(exc)],replay=None,limits=LIMITS)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix('.tmp')
    temp.write_text(json.dumps(report,ensure_ascii=False,allow_nan=False)+'\n')
    temp.replace(args.output)
    print(json.dumps({k:report[k] for k in ('status','seed_count','blocked_reasons')}))
    return 0 if report['status']=='completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
