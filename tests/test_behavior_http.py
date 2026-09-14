"""HTTP contract using explicitly synthetic indexer fixtures, never performance data."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError
from flyhigh.server import make_server


class BehaviorHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'research.snapshot.json'
        self.snapshot = {'fills': [dict(id=i, ts=100+i, wallet='fixture-wallet', token='fixture-token', source='fixture', chain_id=4663, side='buy', usd=10+i) for i in range(1, 4)]}
        self.path.write_text(json.dumps(self.snapshot))
        self.server = make_server(port=0, report={'split': 1, 'generations': [{}]}, directory=self.tmp.name)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_cached_behavior_is_not_replay_and_makes_no_upstream_calls(self):
        with patch('flyhigh.research.refresh_snapshot', side_effect=AssertionError('network forbidden')):
            with urlopen(self.base+'/api/behavior') as response:
                report = json.load(response)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(report['stats']['admitted_fills'], 3)
        self.assertEqual(report['integration_status'], 'awaiting_matching_market_window')
        self.assertTrue(report['candidates'])
        self.assertTrue(all(c['execution'] == 'not_run' for c in report['candidates']))
        self.assertIn('min_liquidity', report['default_genome'])
        self.assertNotIn('replay', report)
        self.assertEqual(json.loads(self.path.read_text()), self.snapshot)
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base+'/api/wallet-replay')
        self.assertEqual(error.exception.code, 503)

    def test_missing_or_invalid_snapshot_is_gracefully_unavailable(self):
        for content in ('null', '{', '{"fills":null}'):
            self.path.write_text(content)
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base+'/api/behavior')
            self.assertEqual(error.exception.code, 503)
            self.assertEqual(json.load(error.exception)['status'], 'unavailable')
        self.path.unlink()
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base+'/api/behavior')
        self.assertEqual(error.exception.code, 503)
