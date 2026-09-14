"""Offline wallet-seeded COPY replay; indexer USD values are not quote fills."""
import argparse
import hashlib
import json
from pathlib import Path
from .data import validate
from .engine import SeedGenome, evolve
from .wallet_rules import map_wallet_to_genome

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/wallet-seeded.report.json'


def build_replay(snapshot, copy_report, histories=None):
    """histories: optional list of canonical fill lists, one wallet/chain/quote each.

    Explicit supplied histories are caller-attested observations, not authenticated
    by this utility. Never convert indexer USD estimates into quote execution.
    """
    payload = snapshot['payload']
    if not isinstance(payload, dict) or not isinstance(payload.get('fills'), list):
        raise ValueError('invalid research payload')
    if (copy_report.get('mode') != 'historical_prices_assumed_liquidity'
            or copy_report.get('execution') != 'simulated'
            or copy_report.get('source', {}).get('symbol') != 'COPY'):
        raise ValueError('expected original historical COPY paper report')
    bars = validate(copy_report['bars'])
    if len(bars) < 80:
        raise ValueError('COPY replay needs at least 80 observations')
    cutoff = bars[int(len(bars) * .7) - 1]['timestamp']
    if histories is None:
        histories = []
    if type(histories) is not list:
        raise ValueError('histories must be a list of canonical fill lists')
    seeds, mappings, reasons = [], [], []
    for rows in histories:
        mapped = map_wallet_to_genome(rows, opening_inventory_known_zero=False)
        mappings.append({k: v for k, v in mapped.items() if k != 'genome'})
        if mapped['genome'] is None:
            reasons.append('History has fewer than three buys with evidenced pre-fill quote cash and known fees.')
        elif mapped['provenance']['observed_until'] > cutoff:
            reasons.append('Wallet evidence extends beyond COPY training cutoff; no lookahead seed admitted.')
        else:
            seeds.append(SeedGenome(mapped['genome'], mapped['provenance']))
    if not histories:
        reasons.append('Indexer tape lacks evidenced pre-fill cash, known fees and executed quote_amount; usd is a valuation, not a quote asset amount. No canonical histories supplied.')
    result = {'schema_version': 1, 'status': 'blocked' if not seeds else 'completed',
              'execution': 'not_run' if not seeds else 'simulated',
              'seed_count': len(seeds), 'blocked_reasons': reasons,
              'research_as_of': payload.get('as_of'),
              'indexer_fill_count': len(payload['fills']),
              'indexer_wallet_count': len(payload.get('wallets', [])),
              'copy_bar_count': len(bars), 'training_cutoff': cutoff,
              'copy_source': copy_report['source'], 'mappings': mappings,
              'limits': ['No receipt authentication or strategy recovery.',
                         'COPY prices are historical; liquidity, fees and execution are modeled.',
                         'Allocation proxy only; all other genes retain defaults.',
                         'No claim of wallet profit or out-of-sample predictive power.'],
              'research_warnings': payload.get('warnings', []), 'replay': None}
    if seeds:
        replay = evolve(bars, seed_genomes=seeds,
                        max_gap=copy_report['methodology']['max_gap_seconds'])
        replay.update(mode=copy_report['mode'], source=copy_report['source'])
        result['replay'] = replay
    json.dumps(result, allow_nan=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--histories', type=Path, help='Optional JSON list of canonical fill lists; never auto-filled from tape')
    args = parser.parse_args()
    paths = {'research': ROOT / 'data/research.snapshot.json',
             'copy_report': ROOT / 'examples/copy.report.json',
             'canonical': ROOT / 'examples/canonical.json'}
    try:
        blobs = {key: path.read_bytes() for key, path in paths.items()}
        source = json.loads(blobs['copy_report'])
        if source['source']['sha256'] != hashlib.sha256(blobs['canonical']).hexdigest():
            raise ValueError('COPY canonical source digest mismatch')
        histories = json.loads(args.histories.read_text()) if args.histories else None
        if args.histories and args.histories.resolve() == OUTPUT.resolve():
            raise ValueError('histories input must not be the output path')
        result = build_replay(json.loads(blobs['research']), source, histories)
        result['inputs'] = {k: {'path': str(paths[k].relative_to(ROOT)),
                               'sha256': hashlib.sha256(v).hexdigest()} for k, v in blobs.items()}
        if args.histories:
            result['inputs']['histories'] = {'path': str(args.histories),
                'sha256': hashlib.sha256(args.histories.read_bytes()).hexdigest()}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'schema_version': 1, 'status': 'blocked', 'execution': 'not_run',
                  'seed_count': 0, 'blocked_reasons': [str(exc)], 'replay': None}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'seed_count', 'blocked_reasons')}))
    return 2 if result['status'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
