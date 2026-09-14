import unittest
import tempfile
from pathlib import Path
import json
import copy


from flyhigh import market_history as mh


class MarketHistoryTests(unittest.TestCase):
    def test_refresh_load_and_identity(self):
        source = mh.SOURCE
        pool = {'data': {'id': source['chain']+'_'+source['pool'], 'attributes': {'address': source['pool']}, 'relationships': {'base_token': {'data': {'id': source['chain']+'_'+source['token']}}}}}
        candles = {'meta': {'base': {'address': source['token']}}, 'data': {'attributes': {'ohlcv_list': [[0,1,2,1,2,3], [600,2,3,1,2,4]]}}}
        calls = []
        def fetch(url):
            calls.append(url)
            return json.dumps(candles if '/ohlcv/' in url else pool).encode()
        with tempfile.TemporaryDirectory() as tmp:
            doc = mh.refresh(tmp, window_count=80, as_of=1000, fetch=fetch)
            self.assertEqual(doc['window']['requested_count'], 80)
            self.assertEqual(doc['quality']['gaps_over_300_seconds'], 1)
            self.assertEqual(mh.load(tmp, as_of=500)['bars'][0]['timestamp'], 300)
            self.assertEqual(len(mh.load(tmp, as_of=500)['bars']), 1)
            self.assertIn('limit=80', calls[1])
            self.assertEqual(len(list(Path(tmp).glob('raw/*'))), 2)
            saved = Path(tmp) / 'copy.latest.json'
            original = saved.read_text()
            corrupt = json.loads(original)
            corrupt['bars'][0]['timestamp'] += 300
            saved.write_text(json.dumps(corrupt))
            with self.assertRaises(ValueError):
                mh.load(tmp)
            saved.write_text(original)
            raw_path = Path(tmp) / doc['raw_sources'][0]['file']
            raw_path.write_bytes(b'{}')
            with self.assertRaises(ValueError):
                mh.load(tmp)
            candles['meta']['base']['address'] = 'wrong'
            with self.assertRaises(ValueError):
                mh.refresh(tmp, as_of=1000, fetch=fetch)
            candles['meta']['base']['address'] = source['token']
            pool['data']['id'] = 'wrong'
            with self.assertRaises(ValueError):
                mh.refresh(tmp, as_of=1000, fetch=fetch)

    def test_reject_bad_rows(self):
        for row in [[0,1,2,1,float('nan'),3], [0,1,0,1,2,3], [0,1,2,1,2,-1], [1,1,2,1,2,3]]:
            with self.assertRaises(ValueError):
                mh.canonicalize([row], as_of=1000)
        with self.assertRaises(ValueError):
            mh.canonicalize([[0,1,2,1,2,3], [0,1,2,1,2,4]], as_of=1000)

    def test_closed_deduplicated_gaps(self):
        rows = [[0, 1, 2, 1, 2, 3], [600, 2, 3, 1, 2, 4],
                [600, 2, 3, 1, 2, 4], [900, 2, 3, 1, 2, 4]]
        bars = mh.canonicalize(rows, as_of=1000)
        self.assertEqual([b['timestamp'] for b in bars], [300, 900])
        self.assertEqual([b['open_timestamp'] for b in bars], [0, 600])
        self.assertEqual(bars[1]['timestamp'] - bars[0]['timestamp'], 600)
