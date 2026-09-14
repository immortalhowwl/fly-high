import unittest
from flyhigh import data

class DataTests(unittest.TestCase):
    def test_validate_series(self):
        bars = data.validate([{'timestamp': 1, 'price': 2, 'liquidity': 100}, {'timestamp': 3, 'price': 3, 'liquidity': 100}])
        self.assertEqual([b['timestamp'] for b in bars], [1,3])
        for bad in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                data.validate([{'timestamp':1,'price':bad,'liquidity':100}])
        with self.assertRaises(ValueError):
            data.validate([bars[1], bars[0]])

class ExecutionTests(unittest.TestCase):
    def test_causal_fills_costs_and_gap(self):
        from flyhigh.engine import simulate, Genome
        bars = data.validate([{'timestamp':1+i*60,'price':100,'liquidity':100000} for i in range(12)])
        g = Genome(momentum=-0.02, lookback=2, hold=3, min_liquidity=100)
        run = simulate(g, bars)
        self.assertGreater(len(run['trades']), 0)
        self.assertLess(run['equity'], 1000)
        self.assertTrue(all(t['timestamp'] > t['signal_timestamp'] for t in run['trades']))
        changed = [dict(b) for b in bars]
        changed[-1]['price'] = 900
        other = simulate(g, changed)
        self.assertEqual(run['decisions'][:-1], other['decisions'][:-1])
        gap = [dict(b) for b in bars]
        for b in gap[3:]: b['timestamp'] += 600
        r = simulate(g, gap)
        self.assertTrue(any(e['action']=='cancel' for e in r['decisions']))
        self.assertTrue(all(t['notional'] <= t['liquidity']*0.01+1e-8 for t in run['trades'] if t['side']=='buy'))

class EvolutionTests(unittest.TestCase):
    def test_reproducible_training_frozen_holdout_and_lineage(self):
        from flyhigh.engine import evolve, BOUNDS
        bars = data.synthetic(count=160)
        a = evolve(bars, seed=7, population=10, generations=3)
        self.assertEqual(a, evolve(bars, seed=7, population=10, generations=3))
        changed = [dict(b) for b in bars]
        for b in changed[112:]: b['price'] *= 10
        b = evolve(changed, seed=7, population=10, generations=3)
        self.assertEqual(a['generations'], b['generations'])
        self.assertEqual(a['champion']['genome'], b['champion']['genome'])
        self.assertEqual(a['holdout_evaluations'], 1)
        self.assertEqual(set(a['baselines']), {'random','momentum'})
        self.assertTrue(any(e['kind']=='extinction' for e in a['events']))
        for gen in a['generations']:
            self.assertEqual(len(gen['flies']), 10)
            self.assertGreater(len({str(f['genome']) for f in gen['flies']}), 5)
            for fly in gen['flies']:
                for key, val in fly['genome'].items():
                    self.assertTrue(BOUNDS[key][0] <= val <= BOUNDS[key][1])
                for m in fly['mutations']:
                    self.assertNotEqual(m['before'], m['after'])
        self.assertTrue(a['events'][-1]['hash'])

if __name__ == '__main__': unittest.main()
