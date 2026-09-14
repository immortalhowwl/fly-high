"""Invented unit fixtures only, never purported to be fetched wallet receipts."""
import unittest
from flyhigh import wallet_rules as rules


def fill(identity='a', timestamp=100, side='buy', quantity=10, quote_amount=100, **changes):
    row = dict(fill_id=identity, wallet='test-wallet', chain='test-chain', asset='test-token',
               quote_asset='USD', timestamp=timestamp, sequence=0, side=side,
               quantity=quantity, quote_amount=quote_amount, fee_quote=1,
               cash_before=None, evidence_url='https://example.org/receipts/' + identity,
               observed=True)
    row.update(changes)
    row['cash_evidence_url'] = row['evidence_url'] if row['cash_before'] is not None else None
    return row


class FeatureTests(unittest.TestCase):
    def test_fifo_partial_exits_and_closed_lot_returns(self):
        rows = [fill(), fill('b', 160, 'sell', 4, 60, fee_quote=.6),
                fill('c', 400, 'sell', 6, 90, fee_quote=.9)]
        partial = rules.analyze_fills(rows[:2], opening_inventory_known_zero=True)
        self.assertEqual(partial['closed_round_trips'], [])
        self.assertEqual(partial['open_lots'][0]['remaining_quantity'], 6)
        self.assertEqual(partial['realized_exits'][0]['holding_seconds'], 60)
        self.assertAlmostEqual(partial['realized_exits'][0]['net_return'], 19 / 40.4)
        report = rules.analyze_fills(rows, opening_inventory_known_zero=True)
        trip = report['closed_round_trips'][0]
        self.assertAlmostEqual(trip['net_return'], 47.5 / 101)
        self.assertEqual(trip['weighted_holding_seconds'], 204)
        self.assertEqual(trip['last_exit_holding_seconds'], 300)
        self.assertEqual(trip['fill_ids'], ['a', 'b', 'c'])
        self.assertEqual(len(trip['evidence_urls']), 3)
        self.assertEqual(report['open_lots'], [])
        # Never treat known buys as proof of no older, unknown opening lots.
        unknown = rules.analyze_fills(rows)
        self.assertEqual(unknown['closed_round_trips'], [])
        self.assertEqual(unknown['realized_exits'], [])

    def test_multiple_entries_assets_missing_fees_and_unmatched_sells(self):
        rows = [fill(quantity=.1, quote_amount=1, fee_quote=0),
                fill('b', 101, quantity=.2, quote_amount=2, fee_quote=0),
                fill('x', 102, asset='other'),
                fill('c', 103, 'sell', .3, 6, fee_quote=0)]
        report = rules.analyze_fills(rows, opening_inventory_known_zero=True)
        self.assertEqual(len(report['closed_round_trips']), 2)
        self.assertTrue(all(t['net_return'] == 1 for t in report['closed_round_trips']))
        self.assertEqual([lot['asset'] for lot in report['open_lots']], ['other'])
        report = rules.analyze_fills([fill(fee_quote=None), fill('b', 101, 'sell')],
                                     opening_inventory_known_zero=True)
        self.assertIsNone(report['closed_round_trips'][0]['net_return'])
        self.assertIn('unknown_fees', report['uncertainties'])
        rows = [fill(side='sell'), fill('b', 101), fill('c', 102, 'sell')]
        report = rules.analyze_fills(rows, opening_inventory_known_zero=True)
        self.assertEqual(report['closed_round_trips'], [])
        self.assertIn('unmatched_sell: test-token', report['uncertainties'])
        self.assertEqual(report['unattributed_sell_ids'], ['a', 'c'])

    def test_allocation_requires_cash_and_fee_denominators(self):
        report = rules.analyze_fills([fill(), fill('b', 101, cash_before=1000),
                                     fill('c', 102, cash_before=1000, fee_quote=None)])
        self.assertEqual(len(report['buy_allocations']), 1)
        self.assertAlmostEqual(report['buy_allocations'][0]['fraction'], .101)
        self.assertEqual(report['buy_allocations'][0]['fill_ids'], ['b'])
        self.assertEqual(report['buy_allocations'][0]['evidence_urls'], ['https://example.org/receipts/b'])
        self.assertTrue(report['insufficient_history'])
        self.assertIn('unknown_cash_before', report['uncertainties'])
        self.assertIn('unknown_fees', report['uncertainties'])
        self.assertIn('unknown_opening_inventory', report['uncertainties'])
        self.assertEqual(rules.analyze_fills([])['status'], 'insufficient_history')
        with self.assertRaises(ValueError): rules.analyze_fills([fill(cash_before=50)])
        with self.assertRaises(ValueError): rules.analyze_fills([], opening_inventory_known_zero='yes')


class MappingTests(unittest.TestCase):
    def test_only_cash_allocation_maps_with_evidence_and_bounds(self):
        from flyhigh.engine import Genome
        rows = [fill(str(i), 100+i, cash_before=200) for i in range(3)]
        mapped = rules.map_wallet_to_genome(rows)
        self.assertEqual(mapped['genome'], Genome(allocation=.5))
        signal = mapped['mapped_genes']['allocation']
        self.assertEqual(signal['observed_value'], .505)
        self.assertTrue(signal['clipped'])
        self.assertEqual(signal['sample_count'], 3)
        self.assertEqual(signal['fill_ids'], ['0', '1', '2'])
        self.assertEqual(len(signal['evidence_urls']), 3)
        self.assertEqual(set(mapped['unmapped_genes']), {'stop', 'take', 'hold', 'momentum', 'lookback', 'min_liquidity'})
        self.assertEqual(mapped['provenance']['kind'], 'wallet_observations')
        self.assertEqual(mapped['provenance']['observed_until'], 102)
        self.assertEqual(mapped['provenance']['mapped_genes'], mapped['mapped_genes'])
        self.assertIsNone(rules.map_wallet_to_genome(rows[:2])['genome'])
        self.assertIsNone(rules.map_wallet_to_genome([fill()])['genome'])
        low = rules.map_wallet_to_genome([fill(str(i), 100+i, cash_before=10000) for i in range(3)])
        self.assertEqual(low['genome'].allocation, .05)


class ValidationTests(unittest.TestCase):
    def test_cash_balance_provenance_and_derived_numeric_safety(self):
        row = fill(cash_before=1000)
        with self.assertRaises(ValueError): rules.validate_fills(row)
        with self.assertRaises(ValueError): rules.validate_fills([{**row, 'cash_evidence_url': None}])
        with self.assertRaises(ValueError): rules.validate_fills([{**row, 'cash_evidence_url': 'file:///balance'}])
        with self.assertRaises(ValueError): rules.validate_fills([fill(quantity=10**1000)])
        with self.assertRaises(ValueError):
            rules.analyze_fills([fill(quote_amount=1e-300, fee_quote=0),
                                 fill('b', 101, 'sell', quote_amount=1e300, fee_quote=0)],
                                opening_inventory_known_zero=True)
        row['cash_evidence_url'] = 'https://example.org/balance'
        sample = rules.analyze_fills([row])['buy_allocations'][0]
        self.assertIn(row['cash_evidence_url'], sample['evidence_urls'])

    def test_strict_schema_and_order(self):
        a = fill()
        self.assertEqual(rules.validate_fills([a]), [a])
        for field, values in {'quantity': [0, -1, True, '10', float('nan'), float('inf')],
                              'quote_amount': [0, -1, False], 'fee_quote': [-1, True],
                              'cash_before': [0, -1, False], 'timestamp': [0, True, 1.5],
                              'sequence': [-1, True], 'side': ['BUY', 'transfer'],
                              'observed': [False, 1], 'evidence_url': ['', 'file:///tmp/a'],
                              'wallet': ['', ' a'], 'asset': ['']}.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    rules.validate_fills([{**a, field: value}])
        invalid = [{k: v for k, v in a.items() if k != 'fee_quote'}, {**a, 'price': 10}]
        for row in invalid:
            with self.assertRaises(ValueError): rules.validate_fills([row])
        for rows in ([a, a], [a, fill('b', 99)], [a, fill('b')],
                     [a, fill('b', 101, wallet='other')],
                     [a, fill('b', 101, quote_asset='ETH')]):
            with self.assertRaises(ValueError): rules.validate_fills(rows)
        self.assertEqual(len(rules.validate_fills([a, fill('b', sequence=1)])), 2)
        self.assertEqual(rules.validate_fills([]), [])
        self.assertIsNot(rules.validate_fills([a])[0], a)
