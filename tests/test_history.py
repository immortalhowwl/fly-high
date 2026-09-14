import unittest
from flyhigh import engine


class HistoryTests(unittest.TestCase):
    def test_import_requires_explicit_assumption_and_uses_close_time(self):
        from flyhigh.import_history import adapt
        asset = {'interval_seconds': 300, 'bars': [
            {'timestamp': 1000, 'close': 2}, {'timestamp': 1900, 'close': 3}],
            'liquidity_snapshot': {'usd': 999999, 'historical': False}}
        with self.assertRaises(ValueError):
            adapt(asset)
        rows = adapt(asset, assumed_liquidity=10000)
        self.assertEqual(rows, [{'timestamp': 1300., 'price': 2., 'liquidity': 10000.},
                                {'timestamp': 2200., 'price': 3., 'liquidity': 10000.}])
        with self.assertRaises(ValueError):
            adapt(asset, assumed_liquidity=float('nan'))

    def test_interval_is_configurable_in_evolution(self):
        bars = [{'timestamp': 1700000000 + i * 300, 'price': 1 + i / 100,
                 'liquidity': 10000} for i in range(100)]
        result = engine.evolve(bars, population=6, generations=1, max_gap=300)
        self.assertEqual(result['methodology']['max_gap_seconds'], 300)
        self.assertTrue(result['baselines']['momentum']['trades'])
