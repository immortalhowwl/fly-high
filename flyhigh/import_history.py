"""Replay real OHLCV closes under an explicitly assumed execution-liquidity scenario."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from .data import validate
from .engine import evolve


def adapt(asset, assumed_liquidity=None):
    if assumed_liquidity is None:
        raise ValueError('Historical liquidity is unknown: explicitly supply --assumed-liquidity')
    liquidity = float(assumed_liquidity)
    interval = float(asset['interval_seconds'])
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError('invalid interval_seconds')
    # A completed close becomes observable at interval end, never at interval start.
    # Gaps are retained; current liquidity_snapshot is deliberately never consulted.
    return validate([{'timestamp': float(b['timestamp']) + interval,
                      'price': b['close'], 'liquidity': liquidity} for b in asset['bars']])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='canonical OHLCV JSON, assets array')
    parser.add_argument('--symbol', default='COPY')
    parser.add_argument('--assumed-liquidity', type=float, required=True,
                        help='constant USD execution scenario, NOT historical liquidity')
    parser.add_argument('--output', default='data/history.report.json')
    parser.add_argument('--seed', type=int, default=17)
    args = parser.parse_args()
    source = Path(args.input).read_bytes()
    doc = json.loads(source)
    matches = [a for a in doc['assets'] if a['symbol'] == args.symbol]
    if len(matches) != 1:
        parser.error('symbol must identify exactly one asset')
    asset = matches[0]
    bars = adapt(asset, args.assumed_liquidity)
    report = evolve(bars, seed=args.seed, max_gap=asset['interval_seconds'])
    report.update(mode='historical_prices_assumed_liquidity', execution='simulated',
                  source={'file': Path(args.input).name, 'sha256': hashlib.sha256(source).hexdigest(),
                          'symbol': asset['symbol'], 'token': asset['token'], 'pool': asset['pool'],
                          'chain': asset['chain'], 'provider': doc['source'],
                          'source_url': asset.get('source_url'), 'collected_at': doc.get('collected_at')})
    report['methodology'].update(historical_liquidity=False,
        assumed_execution_liquidity_usd=args.assumed_liquidity,
        timestamp='completed candle close time = source interval start + interval_seconds',
        execution_warning='Real closes, hypothetical fills. Liquidity is assumed, not observed. No alpha claim.',
        missing_intervals='not interpolated; gaps longer than one interval cancel pending fills and block entries')
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    summary = {'mode': report['mode'], 'bars': len(bars), 'split': report['split'],
        'champion': report['champion']['id'], 'holdout_return': report['holdout']['return'],
        'holdout_fills': len(report['holdout']['trades']), 'holdout_drawdown': report['holdout']['drawdown'],
        'holdout_fees': report['holdout']['fees'],
        'baselines': {k: {'return': v['return'], 'fills': len(v['trades'])} for k,v in report['baselines'].items()}}
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
