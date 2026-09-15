import unittest
from importlib import import_module

A='0x'+'a'*40
B='0x'+'b'*40
T='0x'+'c'*40

def snapshot():
    return {'as_of':'2026-09-15T00:00:00Z','coverage':{'since':100,'until':200,'endpoints':{'tape':{'fetched_at':'2026-09-14T23:59:00Z','stale':False}}},'wallets':[{'address':A,'handle':'alpha'},{'address':B,'handle':'beta'}], 'fills':[]}
def fill(id=1,**kw):
    return dict({'id':id,'wallet':A,'token':T,'ts':150,'chain_id':4663,'side':'buy','priced':'cash_leg','source':'robinhoodtrenches','symbol':'TEST','flags':[],'tx':'0x'+'1'*64},**kw)

class ObservationTests(unittest.TestCase):
    def build(self,s):
        try: module=import_module('flyhigh.observations')
        except ModuleNotFoundError: self.fail('Observation rules module is not implemented')
        return module.build_observations(s)

    def test_three_rules_use_distinct_wallets_and_real_admitted_rows(self):
        s=snapshot();s['fills']=[fill(),fill(),fill(2),fill(3,wallet=B),fill(4,side='sell'),fill(5,priced='no_cash_leg'),fill(6,flags=['not a real buy (planted)']),fill(7,ts=201),fill(8,wallet='0x'+'d'*40)]
        d=self.build(s)
        self.assertEqual(d['counts']['events'],4)
        self.assertEqual(d['counts']['buys'],3)
        self.assertEqual(d['counts']['sells'],1)
        self.assertEqual(d['counts']['groups'],1)
        self.assertEqual(d['groups'][0]['wallets'],[A,B])
        self.assertEqual(d['groups'][0]['event_ids'],['1','2','3'])
        self.assertEqual(d['exits'][0]['id'],'4')
        self.assertEqual(d['window'],{'since':100,'until':200,'label':'Bounded source tape; not a complete 7-day history'})
        self.assertFalse(d['execution_enabled'])
        self.assertIn('/tx/',d['events'][0]['transaction_url'])

    def test_missing_window_and_invalid_rows_are_not_signals(self):
        s=snapshot();s['fills']=[fill(1,ts=float('nan')),fill(2,chain_id=1),fill(3,priced=None),fill(4,flags=['airdrop']),fill(5,kind='transfer'),fill(6,token='invalid'),fill(7,source='unknown')]
        self.assertEqual(self.build(s)['events'],[])
        s['fills']=[fill()];s['coverage'].pop('since')
        self.assertEqual(self.build(s)['groups'],[])
        self.assertEqual(self.build(s)['status'],'empty')

    def test_http_observations_and_default_page_preserve_explicit_replays(self):
        import json,threading
        from urllib.request import urlopen
        from unittest.mock import patch
        from flyhigh.server import make_server
        with patch('flyhigh.research.load_snapshot',return_value=snapshot()):
            server=make_server(0)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(base+'/') as r: default=r.read().decode()
                self.assertIn('FOLLOW TRADER',default)
                self.assertNotIn('src="/app.js"',default)
                for mode in ['hypothesis','wallet','archive']:
                    with urlopen(base+'/?replay='+mode) as r: old=r.read().decode()
                    self.assertIn('src="/app.js"',old)
                    self.assertIn('hero-video',old)
                with urlopen(base+'/api/observations') as r: data=json.load(r)
                self.assertEqual(data['counts']['roster'],2)
                self.assertFalse(data['execution_enabled'])
                for path in ['/observation.js','/observation.css']:
                    with urlopen(base+path) as r:self.assertEqual(r.status,200)
            finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
