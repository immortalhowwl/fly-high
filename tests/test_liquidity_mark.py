import unittest
from flyhigh.engine import Genome, simulate

class LiquidityMarkTests(unittest.TestCase):
    def test_inventory_not_counted_as_fully_liquidatable_when_depth_collapses(self):
        bars=[{'timestamp':1000+i*60,'price':p,'liquidity':liq} for i,(p,liq) in enumerate([(100,100000),(100,100000),(101,100000),(101,100000),(10000,100)])]
        r=simulate(Genome(lookback=2,momentum=-.02,min_liquidity=100,allocation=.2),bars)
        self.assertLessEqual(r['equity'],r['cash']+1)
        self.assertGreater(r['mark_to_market_equity'],r['equity'])
