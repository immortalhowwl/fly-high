import copy
import unittest
from flyhigh.wallet_history import WalletHistory, build_history

A = '0x' + 'a' * 40
T = '0x' + 'b' * 40
W = {'address': A, 'handle': 'known'}

def source():
    return {'address': A, 'chain': 'robinhood', 'positions': [dict(token=T, sym='ALPHA', chain='robinhood', buys=9, sells=2, bought_usd=123, sold_usd=20, first_ts=10, last_ts=20)], 'closed': [], 'fills': [{'kind': 'dust'}, {'kind': 'trade', 'priced': 'no_cash_leg'}]}

class HistoryTests(unittest.TestCase):
    def test_group_scope_identity_and_no_generated_claims(self):
        d=source(); d.update(summary='invented profit', score=100)
        r=build_history(W,d,captured_at=100)
        self.assertIn('ALPHA: 9 buys and 2 sells',r['takeaway'])
        self.assertNotIn('invented',str(r)); self.assertNotIn('score',r)
        self.assertIn('NOT restricted',r['scope']['grouped'])
        self.assertEqual(r['scope']['excluded_recent_fill_count'],2)
        for change in [{'address':T},{'chain':'solana'}]:
            with self.assertRaises(ValueError): build_history(W,dict(d,**change))

    def test_mixed_chain_flagged_and_duplicate_groups(self):
        d=source(); p=d['positions'][0]
        d['positions'] += [dict(p,chain='bsc',sym='BAD'),dict(p,token='0x'+'c'*40,priced='no_cash_leg'),dict(p)]
        r=build_history(W,d)
        self.assertEqual(len(r['groups']),1); self.assertNotIn('BAD',r['takeaway'])
        self.assertEqual(r['scope']['rejected_group_count'],2)

    def test_cache_stale_and_unknown_no_network(self):
        calls=[]
        def fetch(url):
            calls.append(url)
            return source() if 'fomoradar' in url else {'address':A,'history':[]}
        c=WalletHistory(fetch)
        snapshot={'wallets':[W]}
        with self.assertRaises(KeyError): c.get('https://evil',snapshot)
        self.assertEqual(calls,[])
        r=c.get(A,snapshot); self.assertEqual(len(calls),2)
        c.get(A,snapshot); self.assertEqual(len(calls),2)
        c.ttl=-1
        def fail(url): raise OSError('offline')
        c.fetch=fail
        stale=c.get(A,snapshot)
        self.assertTrue(stale['stale']); self.assertEqual(stale['captured_at'],r['captured_at'])

    def test_receipt_links_do_not_validate_group(self):
        f={'wallet':A,'token':T,'tx':'0x'+'1'*64,'priced':'no_cash_leg'}
        r=build_history(W,source(),recent_fills=[f,dict(f,wallet=T)])
        tx=r['groups'][0]['transactions']
        self.assertEqual(len(tx),1)
        self.assertEqual(tx[0]['classification'],'excluded_transfer_or_no_cash_leg')

    def test_http_route_and_unknown_wallet(self):
        import json
        import threading
        from urllib.request import urlopen
        from urllib.error import HTTPError
        from unittest.mock import patch
        from flyhigh.server import make_server
        report = build_history(W, source())
        with patch('flyhigh.research.load_snapshot', return_value={'wallets': [W]}), patch('flyhigh.wallet_history.WalletHistory.get', return_value=report) as get:
            server = make_server(0)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                url = f'http://127.0.0.1:{server.server_port}/api/wallet-history/{A}'
                result = json.load(urlopen(url))
                self.assertEqual(result['wallet'], A)
                self.assertIn('ALPHA', result['takeaway'])
                get.side_effect = KeyError('unknown')
                with self.assertRaises(HTTPError) as caught: urlopen(url)
                self.assertEqual(caught.exception.code, 404)
            finally:
                server.shutdown(); server.server_close()

    def test_native_identity_rejected(self):
        with self.assertRaises(ValueError): build_history(W,source(),{'address':T})

if __name__=='__main__': unittest.main()
