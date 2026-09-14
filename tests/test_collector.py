import unittest
from flyhigh import collector

class CollectorTests(unittest.TestCase):
    def test_network_identity_and_finite_values(self):
        pair={'chainId':'robinhood','pairAddress':'pool','baseToken':{'address':'token','symbol':'FLY'},'quoteToken':{'address':'usd','symbol':'USD'},'priceUsd':'0.2','liquidity':{'usd':20000}}
        doc={'pairs':[pair,dict(pair,chainId='solana'),dict(pair,priceUsd='NaN')]}
        result=collector.decode(doc, 1234)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['token_address'],'token')
        self.assertEqual(result[0]['timestamp'],1234)
        self.assertEqual(collector.decode({'pairs':[]},1234),[])

if __name__=='__main__': unittest.main()
