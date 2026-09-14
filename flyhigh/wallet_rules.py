"""Offline observed-fill boundary; no provider, wallet connection, or authenticity oracle.

See data/wallet-layer-handoff.md for the canonical schema and accounting assumptions.
Evidence URLs are carried through, never fetched or authenticated here.
"""
import math
import json
from decimal import Decimal

from urllib.parse import urlsplit

FIELDS = frozenset(('fill_id', 'wallet', 'chain', 'asset', 'quote_asset', 'timestamp',
                    'sequence', 'side', 'quantity', 'quote_amount', 'fee_quote',
                    'cash_before', 'cash_evidence_url', 'evidence_url', 'observed'))


def validate_fills(rows):
    """Copy a strict, ordered, single-wallet/chain/quote list. Empty is valid history."""
    if type(rows) is not list:
        raise ValueError('fills must be a list')
    result, seen, identity, previous = [], set(), None, None
    for row in rows:
        if type(row) is not dict or set(row) != FIELDS:
            raise ValueError('fill must contain exactly the canonical fields')
        for key in ('fill_id', 'wallet', 'chain', 'asset', 'quote_asset', 'evidence_url'):
            value = row[key]
            if type(value) is not str or not value or value != value.strip() or any(ord(c) < 32 for c in value):
                raise ValueError('invalid text: ' + key)
        if row['cash_before'] is None and row['cash_evidence_url'] is not None:
            raise ValueError('cash evidence requires known cash_before')
        for key in ('evidence_url', 'cash_evidence_url'):
            if key == 'cash_evidence_url' and row['cash_before'] is None:
                continue
            value = row[key]
            try:
                url = urlsplit(value) if type(value) is str else None
                valid_url = (url and url.scheme in ('http', 'https') and url.hostname
                             and not url.username and not url.password
                             and not any(c.isspace() or ord(c) < 32 for c in value))
            except ValueError:
                valid_url = False
            if not valid_url:
                raise ValueError(key + ' must be an HTTP(S) evidence reference')
        if row['observed'] is not True or row['side'] not in ('buy', 'sell'):
            raise ValueError('only explicitly observed buy/sell fills accepted')
        for key in ('timestamp', 'sequence'):
            if type(row[key]) is not int or row[key] < (1 if key == 'timestamp' else 0):
                raise ValueError('invalid integer: ' + key)
        for key in ('quantity', 'quote_amount', 'fee_quote', 'cash_before'):
            value = row[key]
            if value is None and key in ('fee_quote', 'cash_before'):
                continue
            try:
                finite = type(value) in (int, float) and math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite or value < 0 or (key != 'fee_quote' and value == 0):
                raise ValueError('invalid finite amount: ' + key)
        current_identity = tuple(row[k] for k in ('wallet', 'chain', 'quote_asset'))
        if identity is not None and current_identity != identity:
            raise ValueError('mixed wallet, chain or quote units')
        order = (row['timestamp'], row['sequence'])
        if previous is not None and order <= previous:
            raise ValueError('fills must be strictly ordered by (timestamp, sequence)')
        if row['fill_id'] in seen:
            raise ValueError('duplicate fill_id')
        seen.add(row['fill_id'])
        previous, identity = order, current_identity
        result.append(dict(row))
    return result


def analyze_fills(rows, *, opening_inventory_known_zero=False):
    """Derive only observable features; caller must attest full inventory history.

    The attestation covers ALL listed assets and no missing fills/transfers/rebases.
    Without it no FIFO entry attribution or realized returns are asserted.
    """
    rows = validate_fills(rows)
    if type(opening_inventory_known_zero) is not bool:
        raise ValueError('opening_inventory_known_zero must be boolean')
    uncertainties = {'receipt_authenticity_not_verified', 'strategy_intent_unobservable'}
    if not opening_inventory_known_zero:
        uncertainties.add('unknown_opening_inventory')
    allocations = []
    for row in rows:
        if row['fee_quote'] is None:
            uncertainties.add('unknown_fees')
        if row['side'] == 'buy':
            if row['cash_before'] is None:
                uncertainties.add('unknown_cash_before')
            elif row['fee_quote'] is not None:
                spend = Decimal(str(row['quote_amount'])) + Decimal(str(row['fee_quote']))
                fraction = spend / Decimal(str(row['cash_before']))
                if fraction > 1:
                    raise ValueError('buy spend exceeds known pre-fill cash')
                allocations.append({'fraction': float(fraction), 'fill_ids': [row['fill_id']],
                                    'evidence_urls': list(dict.fromkeys((row['evidence_url'], row['cash_evidence_url'])))})
    exits, trips, unattributed, lots, tainted = [], [], [], {}, set()
    if opening_inventory_known_zero:
        uncertainties.add('fifo_accounting_not_observed_lot_selection')
    for row in rows:
        asset = row['asset']
        if not opening_inventory_known_zero or asset in tainted:
            if row['side'] == 'sell':
                unattributed.append(row['fill_id'])
            continue
        quantity = Decimal(str(row['quantity']))
        quote = Decimal(str(row['quote_amount']))
        fee = None if row['fee_quote'] is None else Decimal(str(row['fee_quote']))
        queue = lots.setdefault(asset, [])
        if row['side'] == 'buy':
            queue.append({'row': row, 'remaining': quantity, 'quantity': quantity,
                          'cost': None if fee is None else quote + fee,
                          'proceeds': Decimal(0), 'fees_known': fee is not None,
                          'duration_sum': Decimal(0), 'fill_ids': [row['fill_id']],
                          'evidence_urls': [row['evidence_url']]})
            continue
        if quantity > sum((lot['remaining'] for lot in queue), Decimal(0)):
            # An inventory contradiction invalidates attribution for this entire
            # sell and subsequent records of this asset, never invent an entry.
            tainted.add(asset)
            uncertainties.add('unmatched_sell: ' + asset)
            unattributed.append(row['fill_id'])
            lots[asset] = []
            continue
        remaining = quantity
        while remaining:
            lot = queue[0]
            matched = min(remaining, lot['remaining'])
            entry_cost = None if lot['cost'] is None else lot['cost'] * matched / lot['quantity']
            proceeds = None if fee is None else (quote - fee) * matched / quantity
            duration = row['timestamp'] - lot['row']['timestamp']
            evidence = [lot['row']['evidence_url'], row['evidence_url']]
            exits.append({'asset': asset, 'quantity': float(matched),
                          'entry_fill_id': lot['row']['fill_id'], 'exit_fill_id': row['fill_id'],
                          'holding_seconds': duration,
                          'net_return': None if entry_cost is None or proceeds is None else float(proceeds / entry_cost - 1),
                          'evidence_urls': evidence})
            lot['fees_known'] = lot['fees_known'] and proceeds is not None
            if proceeds is not None:
                lot['proceeds'] += proceeds
            lot['duration_sum'] += matched * duration
            lot['fill_ids'].append(row['fill_id'])
            lot['evidence_urls'].append(row['evidence_url'])
            lot['remaining'] -= matched
            remaining -= matched
            if not lot['remaining']:
                trips.append({'asset': asset, 'quantity': float(lot['quantity']),
                              'net_return': float(lot['proceeds'] / lot['cost'] - 1) if lot['fees_known'] else None,
                              'weighted_holding_seconds': float(lot['duration_sum'] / lot['quantity']),
                              'last_exit_holding_seconds': duration,
                              'fill_ids': lot['fill_ids'],
                              'evidence_urls': list(dict.fromkeys(lot['evidence_urls']))})
                queue.pop(0)
    open_lots = [{'asset': asset, 'entry_fill_id': lot['row']['fill_id'],
                  'remaining_quantity': float(lot['remaining']),
                  'evidence_urls': [lot['row']['evidence_url']]}
                 for asset, queue in lots.items() for lot in queue]
    if open_lots:
        uncertainties.add('open_inventory_right_censored')
    sufficient_allocations = len(allocations) >= 3
    sufficient_trips = sum(t['net_return'] is not None for t in trips) >= 3
    insufficient = not (sufficient_allocations and sufficient_trips)
    report = {'schema_version': 1, 'status': 'insufficient_history' if insufficient else 'observations_available',
            'insufficient_history': insufficient,
            'feature_sufficiency': {'allocation': sufficient_allocations, 'closed_returns': sufficient_trips},
            'closed_round_trips': trips, 'realized_exits': exits, 'open_lots': open_lots,
            'unattributed_sell_ids': unattributed,
            'wallet': rows[0]['wallet'] if rows else None,
            'chain': rows[0]['chain'] if rows else None,
            'quote_asset': rows[0]['quote_asset'] if rows else None,
            'observed_until': rows[-1]['timestamp'] if rows else None,
            'fill_count': len(rows), 'buy_allocations': allocations,
            'uncertainties': sorted(uncertainties)}
    # Finite input values can still produce ratios outside binary64 output range.
    json.dumps(report, allow_nan=False)
    return report


def map_wallet_to_genome(rows, *, opening_inventory_known_zero=False):
    """A bounded allocation candidate, NOT recovered strategy or profit prediction.

    Three known-cash fills is a transparent minimal sample gate, not statistical
    confidence. Unsupported genes retain engine defaults explicitly, not estimates.
    """
    from statistics import median
    from .engine import Genome, BOUNDS

    report = analyze_fills(rows, opening_inventory_known_zero=opening_inventory_known_zero)
    mapped, genome = {}, None
    unmapped = {
        'stop': 'Realized losses do not identify a stop trigger.',
        'take': 'Realized gains do not identify a take-profit trigger.',
        'hold': 'Observed durations are not a maximum holding rule; engine uses observation counts, not seconds.',
        'momentum': 'No decision-time market context or rejected entries.',
        'lookback': 'No observed signal window.',
        'min_liquidity': 'Fill size does not reveal a liquidity threshold.',
    }
    if report['feature_sufficiency']['allocation']:
        samples = report['buy_allocations']
        observed = median(s['fraction'] for s in samples)
        low, high = BOUNDS['allocation']
        value = max(low, min(high, observed))
        mapped['allocation'] = {
            'observed_value': observed, 'value': value, 'clipped': value != observed,
            'sample_count': len(samples), 'method': 'median((quote_amount + fee_quote) / cash_before)',
            'fill_ids': [s['fill_ids'][0] for s in samples],
            'evidence_urls': list(dict.fromkeys(url for s in samples for url in s['evidence_urls'])),
            'limitation': 'Executed cash fraction only; liquidity caps and split orders may hide intended allocation.',
        }
        genome = Genome(allocation=value)
    else:
        unmapped['allocation'] = 'Need at least three observed buys with known pre-fill quote cash and fees.'
    provenance = {
        'kind': 'wallet_observations', 'schema_version': 1,
        'wallet': report['wallet'], 'chain': report['chain'], 'quote_asset': report['quote_asset'],
        'observed_until': report['observed_until'], 'mapped_genes': mapped,
        'unmapped_genes': unmapped, 'uncertainties': report['uncertainties'],
        'disclaimer': 'Observable behavioral proxy only; not copying a brain, intent, or guaranteed profitable strategy.',
    }
    return {'genome': genome, 'mapped_genes': mapped, 'unmapped_genes': unmapped,
            'provenance': provenance, 'analysis': report}
