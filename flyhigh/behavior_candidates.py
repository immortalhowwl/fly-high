"""Indexer behavior -> token-bound paper hypotheses, never recovered wallet rules.

Pure/read-only; deliberately independent of the strict wallet_rules fill contract.
"""
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import math
from statistics import median

from .engine import BOUNDS, Genome, SeedGenome


DISCLAIMER = ('wallet-inspired hypothesis; not a verified cloned strategy, wallet allocation, '
              'intent, profit estimate or recommendation. Indexer observations are partial.')


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _capture_epoch(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def _distribution(rows):
    valid = [r for r in rows if _positive(r.get('usd'))]
    values = sorted(r['usd'] for r in valid)
    # Linear interpolation quantiles, index (n-1)*q.
    def quantile(q):
        if not values:
            return None
        index = (len(values)-1)*q
        lo, hi = math.floor(index), math.ceil(index)
        return values[lo]*(1-(index-lo)) + values[hi]*(index-lo)
    return {'unit': 'source_estimated_USD', 'sample_count': len(values),
            'missing_or_invalid_count': len(rows)-len(values),
            'min': min(values) if values else None, 'p25': quantile(.25),
            'median': quantile(.5), 'p75': quantile(.75),
            'max': max(values) if values else None,
            'event_ids': [r['id'] for r in valid],
            'formula': 'linear interpolation at (n-1)*q; positive finite usd only'}


def build_behavior_candidates(snapshot, *, evidence_cutoff=None):
    """Accept research envelope OR canonical DTO. Return finite JSON report.

    evidence_cutoff filters event time only (inclusive UNIX seconds), NOT knowledge
    time. Missing capture time preserves features but prevents causal seed export.
    Candidate experiment: engine minimum liquidity sufficient for a source-sized
    order at engine's 1% depth cap. This is NOT an observed liquidity preference.
    """
    if evidence_cutoff is not None and (type(evidence_cutoff) is not int or evidence_cutoff <= 0):
        raise ValueError('evidence_cutoff must be positive integer seconds')
    payload = snapshot.get('payload', snapshot)
    if not isinstance(payload.get('fills'), list):
        raise ValueError('expected research fills list')
    tape = payload.get('coverage', {}).get('endpoints', {}).get('tape', {})
    raw_tape = snapshot.get('raw', {}).get('tape', {})
    attribution = {k: tape.get(k) for k in ('url', 'fetched_at', 'stale')}
    attribution['raw_sha256'] = raw_tape.get('sha256')
    attribution['kind'] = 'indexer_reported_not_receipt_verified'
    captured = _capture_epoch(attribution['fetched_at'])
    groups, seen = defaultdict(list), {}
    rejected, duplicates, future = 0, 0, 0
    for row in payload['fills']:
        if (not isinstance(row, dict) or type(row.get('id')) is not int
                or type(row.get('ts')) is not int or row['ts'] <= 0
                or row.get('side') not in ('buy', 'sell')
                or any(not isinstance(row.get(k), str) or not row[k] for k in ('wallet', 'token', 'source'))
                or type(row.get('chain_id')) is not int):
            rejected += 1
            continue
        if evidence_cutoff is not None and row['ts'] > evidence_cutoff:
            future += 1
            continue
        key = (row['source'], row['chain_id'], row['id'])
        if key in seen:
            if seen[key] != row:
                raise ValueError('conflicting duplicate source event ID')
            duplicates += 1
            continue
        seen[key] = row
        groups[(row['source'], row['chain_id'], row['wallet'])].append(row)
    wallets, candidates = [], []
    for (source, chain, wallet), rows in sorted(groups.items()):
        rows.sort(key=lambda r: (r['ts'], r['id']))
        buys = [r for r in rows if r['side'] == 'buy']
        counts = Counter(r['token'] for r in buys)
        intervals = [b['ts']-a['ts'] for a, b in zip(rows, rows[1:])]
        features = {
            'wallet': wallet, 'chain_id': chain, 'source': source,
            'provenance_class': 'DERIVED', 'attribution': attribution,
            'window': {'since': rows[0]['ts'], 'until': rows[-1]['ts'],
                       'complete_history': False, 'requested_event_cutoff': evidence_cutoff},
            'event_ids': [r['id'] for r in rows],
            'events': [dict({k: r.get(k) for k in ('id', 'ts', 'tx', 'token', 'side', 'priced')},
                            usd=r.get('usd') if _positive(r.get('usd')) else None) for r in rows],
            'buy_count': len(buys), 'sell_count': len(rows)-len(buys),
            'buy_token_concentration': {
                'denominator': 'observed buy event count, NOT cash or portfolio weight',
                'counts': dict(sorted(counts.items())),
                'shares': {k: v/len(buys) for k, v in sorted(counts.items())},
                'hhi': sum((v/len(buys))**2 for v in counts.values()) if buys else None},
            'cadence': {'unit': 'seconds_between_observed_events', 'intervals': intervals,
                        'median': median(intervals) if intervals else None,
                        'zero_interval_count': intervals.count(0),
                        'missing_intervals_count': 0 if intervals else 1,
                        'limitation': 'Not holding time, decision frequency or engine observation count.'},
            'order_size_usd': _distribution(rows), 'buy_order_size_usd': _distribution(buys),
            'missingness': ['cash_before', 'fees', 'opening_inventory', 'decision_context',
                            'complete_history', 'observed_liquidity'],
        }
        wallets.append(features)
        for token in sorted(counts):
            token_rows = [r for r in buys if r['token'] == token]
            sizes = _distribution(token_rows)
            if sizes['sample_count'] < 3:
                continue
            used = set()
            for quantile in ('p25', 'median', 'p75'):
                observed = sizes[quantile]
                unbounded = observed / .01
                low, high = BOUNDS['min_liquidity']
                value = max(low, min(high, unbounded))
                if value in used:
                    continue
                used.add(value)
                genome = asdict(Genome(min_liquidity=value))
                mapped = {'min_liquidity': {
                    'classification': 'HYPOTHESIZED_PARAMETER', 'value': value,
                    'observed_feature': 'positive source-estimated buy USD ' + quantile,
                    'observed_value': observed, 'unbounded_value': unbounded,
                    'clipped': value != unbounded, 'quantile': quantile,
                    'formula': 'clip(source_estimated_buy_usd_quantile / 0.01, 100, 50000)',
                    'meaning': 'Experiment with a depth screen sized to observed order scale at the engine 1% cap; NOT recovered wallet liquidity threshold. Clipping may prevent full capacity.',
                    'event_ids': sizes['event_ids']}}
                end = max(r['ts'] for r in rows)
                origin = {'kind': 'wallet_inspired_hypothesis', 'label': 'wallet-inspired hypothesis',
                          'wallet': wallet, 'chain_id': chain, 'token': token, 'source': source,
                          'observed_until': end, 'captured_at': attribution['fetched_at'],
                          'available_after': max(captured, end) if captured is not None else None,
                          'attribution': attribution, 'mapped_genes': mapped,
                          'default_genes': {k: v for k, v in genome.items() if k not in mapped},
                          'event_ids': features['event_ids'], 'evidence_window': features['window'],
                          'disclaimer': DISCLAIMER}
                digest = hashlib.sha256(json.dumps({'genome': genome, 'provenance': origin}, sort_keys=True, allow_nan=False).encode()).hexdigest()
                candidates.append({'id': 'WH-' + digest[:16], 'genome': genome,
                                   'provenance': origin, 'execution': 'not_run'})
    report = {'schema_version': 1, 'status': 'hypotheses_available' if candidates else 'features_only',
              'wallets': wallets, 'candidates': candidates,
              'stats': {'input_fills': len(payload['fills']), 'admitted_fills': len(seen),
                        'rejected_fills': rejected, 'duplicates': duplicates, 'after_cutoff': future,
                        'wallet_count': len(wallets), 'candidate_count': len(candidates)},
              'integration': 'Export only matching chain/token with evaluation_start strictly after available_after. Pass returned SeedGenome objects to evolve(seed_genomes=...). Preserve token price/liquidity provenance; no automatic unrelated COPY replay. Compare to default Genome control under identical execution assumptions. Cadence/concentration need new cooldown/multi-asset genes, not hold/allocation substitutions.',
              'limits': [DISCLAIMER, 'Three priced buys is an experiment sample gate, not confidence.',
                         'Default momentum/stop/take/hold/allocation/lookback are experimental controls, not wallet observations.',
                         'USD estimates do not prove settlement currency or exact order size.']}
    json.dumps(report, allow_nan=False)
    return report


def seed_candidates(report, *, token, chain_id, evaluation_start, limit=24):
    """Return matching causal SeedGenome list; never backdate capture availability.

    Engine does not enforce this hypothesis kind's timestamp boundary itself;
    callers MUST use this export gate rather than constructing SeedGenome directly.
    """
    if type(evaluation_start) is not int or evaluation_start <= 0:
        raise ValueError('evaluation_start must be positive integer seconds')
    if type(limit) is not int or not 1 <= limit <= 64:
        raise ValueError('limit must be 1..64 and no larger than evolve population')
    admitted = []
    for candidate in report['candidates']:
        p = candidate['provenance']
        if p['token'] != token or p['chain_id'] != chain_id:
            continue
        available = p['available_after']
        if available is None or evaluation_start <= available:
            continue
        admitted.append(SeedGenome(Genome(**candidate['genome']), json.loads(json.dumps(p))))
    return admitted[:limit]


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=Path(__file__).resolve().parents[1] / 'data/research.snapshot.json')
    parser.add_argument('--evidence-cutoff', type=int)
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()
    report = build_behavior_candidates(json.loads(args.snapshot.read_text()), evidence_cutoff=args.evidence_cutoff)
    print(json.dumps(report if args.full else {'status': report['status'], **report['stats']}, allow_nan=False))


if __name__ == '__main__':
    main()
