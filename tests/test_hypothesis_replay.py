"""Synthetic protocol fixtures only; production run saved separately, no network in CI."""
from copy import deepcopy
import hashlib
import json
import unittest
from urllib.parse import urlencode

from flyhigh.behavior_candidates import build_behavior_candidates, seed_candidates
from flyhigh.hypothesis_replay import build_replay, select_experiment, verified_bars, KIND
from flyhigh.engine import Genome, simulate

TOKEN = '0x'+'a'*40
POOL = '0x'+'b'*40
WALLET = '0x'+'c'*40
START = 1700000040


def fixture():
    snapshot = {'payload': {'fills': [dict(id=i+1, ts=START+600+i*60, side='buy',
        wallet=WALLET, token=TOKEN, source='test_indexer', chain_id=4663, usd=30+i,
        tx='test-'+str(i)) for i in range(3)], 'tokens': [],
        'coverage': {'endpoints': {'tape': {'url':'https://example.invalid/tape',
        'fetched_at':'2024-01-01T00:00:00+00:00'}}}}}
    _, selection = select_experiment(snapshot)
    cutoff = START+120*60
    prefix = 'https://api.geckoterminal.com/api/v2/networks/robinhood'
    pool_body = {'data':[{'id':'robinhood_'+POOL,'attributes':{'address':POOL},
        'relationships':{'base_token':{'data':{'id':'robinhood_'+TOKEN}}}}]}
    rows = [[START+i*60, 1+i*.01,1+i*.01,1+i*.01,1+i*.01,10] for i in range(120)]
    body = {'meta':{'base':{'address':TOKEN}},'data':{'attributes':{'ohlcv_list':rows}}}
    urls = [f'{prefix}/tokens/{TOKEN}/pools', f'{prefix}/pools/{POOL}/ohlcv/minute?'+urlencode(dict(
        aggregate=1,limit=1000,currency='usd',token=TOKEN,include_empty_intervals='false',before_timestamp=cutoff))]
    sources = []
    for value,url in zip((pool_body,body),urls):
        raw = json.dumps(value)
        sources.append(dict(url=url,raw_body=raw,sha256=hashlib.sha256(raw.encode()).hexdigest(),captured_at='2024-01-01T00:00:00+00:00'))
    market = dict(token=TOKEN,chain='robinhood',chain_id=4663,pool=POOL,as_of=cutoff,
        interval_seconds=60,timestamp_semantics='closed',raw_sources=sources)
    return snapshot,market,selection


def change_body(market, index, change):
    receipt=market['raw_sources'][index]
    obj=json.loads(receipt['raw_body']);change(obj)
    receipt['raw_body']=json.dumps(obj)
    receipt['sha256']=hashlib.sha256(receipt['raw_body'].encode()).hexdigest()


class ReplayTests(unittest.TestCase):
    def test_end_to_end_and_control(self):
        s,m,_=fixture();r=build_replay(s,m);p=r['replay']
        self.assertEqual(r['status'],'completed')
        self.assertEqual(r['seed_count'],3)
        self.assertEqual(len(p['generations']),6)
        self.assertEqual(p['mode'],'historical_prices_assumed_liquidity')
        self.assertFalse(p['methodology']['causal_forward_test'])
        self.assertIn('NOT unseen',p['methodology']['holdout'])
        self.assertEqual(r['control']['train'],simulate(Genome(),p['bars'][:p['split']],max_gap=60))
        f=p['generations'][0]['flies'][0]
        self.assertEqual(f['seed_origin']['provenance']['kind'],KIND)
        self.assertEqual(f['seed_origin']['provenance']['wallet'],WALLET)
        self.assertTrue(any(f['parents'] and f['mutations'] for g in p['generations'] for f in g['flies']))
        self.assertTrue(any(f['result']['trades'] for f in p['generations'][0]['flies']))
        json.dumps(r,allow_nan=False)

    def test_causal_gate_still_blocks(self):
        s,m,_=fixture();b=build_behavior_candidates(s)
        self.assertEqual(seed_candidates(b,token=TOKEN,chain_id=4663,evaluation_start=START),[])
        self.assertEqual(build_replay(s,m)['status'],'completed')

    def test_determinism(self):
        s,m,_=fixture();self.assertEqual(build_replay(s,m),build_replay(s,m))

    def test_chain_token_identity(self):
        for key,value in [('chain_id',1),('token','0xwrong'),('chain','eth'),('timestamp_semantics','open')]:
            s,m,_=fixture();m[key]=value
            with self.assertRaises(ValueError):build_replay(s,m)

    def test_receipt_integrity(self):
        s,m,_=fixture();m['raw_sources'][1]['raw_body']+=' '
        with self.assertRaisesRegex(ValueError,'digest'):build_replay(s,m)

    def test_provider_identity(self):
        s,m,_=fixture();change_body(m,1,lambda obj:obj['meta']['base'].update(address='wrong'))
        with self.assertRaisesRegex(ValueError,'metadata'):build_replay(s,m)
        s,m,_=fixture();m['raw_sources'][1]['url']=m['raw_sources'][1]['url'].replace('currency=usd','currency=eth')
        with self.assertRaisesRegex(ValueError,'query'):build_replay(s,m)

    def test_closed_and_gaps(self):
        s,m,sel=fixture()
        def edit(obj):
            rows=obj['data']['attributes']['ohlcv_list'];del rows[10]; rows.append([m['as_of'],2,2,2,2,10])
        change_body(m,1,edit);bars=verified_bars(m,sel)
        self.assertEqual(len(bars),119)
        self.assertEqual(bars[0]['timestamp'],START+60)
        self.assertEqual(bars[-1]['timestamp'],m['as_of'])
        r=build_replay(s,m);self.assertEqual(r['quality']['gaps_over_interval'],1)
        for g in r['replay']['generations']:
            for f in g['flies']:
                self.assertTrue(all(t['timestamp']-t['signal_timestamp']<=60 for t in f['result']['trades']))

    def test_bad_candles(self):
        for bad in ([START,1,0,1,1,10],[START,1,1,1,1,-1],[START,1,1,1,float('nan'),1]):
            s,m,_=fixture();change_body(m,1,lambda obj:obj['data']['attributes']['ohlcv_list'].append(bad))
            with self.assertRaises(ValueError):build_replay(s,m)

    def test_insufficient_no_fallback(self):
        s,m,_=fixture();change_body(m,1,lambda obj:obj['data']['attributes'].update(ohlcv_list=obj['data']['attributes']['ohlcv_list'][:79]))
        with self.assertRaisesRegex(ValueError,'79 closed bars'):build_replay(s,m)

    def test_selection_ignores_market(self):
        s,_,_=fixture();a=select_experiment(s)[1]
        s['payload']['tokens']=[dict(token=TOKEN,liquidity=1,honeypot=True,change24=-99)]
        self.assertEqual(select_experiment(s)[1],a)


if __name__=='__main__':unittest.main()
