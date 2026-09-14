import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from flyhigh import market_history as mh
from flyhigh.server import make_server, research_with_chart, refresh_market


class MarketIntegrationTests(unittest.TestCase):
    def test_canonical_only_package_and_exact_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(mh.DEFAULT_DIR / 'copy.latest.json', tmp)
            doc = mh.load(tmp, verify_raw=False)
            self.assertGreaterEqual(len(doc['bars']), 80)
            snapshot = {'tokens': [{'token': 'other', 'symbol': 'COPY'}, {'token': mh.SOURCE['token'], 'chain': 'wrong'}]}
            result = research_with_chart(snapshot, tmp)
            self.assertNotIn('candles', result['tokens'][0])
            self.assertNotIn('candles', result['tokens'][1])
            self.assertEqual(len(result['tokens'][2]['candles']), len(doc['bars']))
            self.assertEqual(result['tokens'][2]['candles'][0]['ts'], doc['bars'][0]['timestamp'])
            self.assertTrue(result['tokens'][2]['chart_source']['has_gaps'])

    def test_real_http_no_provider_calls(self):
        server = make_server(0, public=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch('flyhigh.market_history.urlopen', side_effect=AssertionError('HTTP must not fetch')), patch('flyhigh.research.urlopen', side_effect=AssertionError('HTTP must not fetch')):
                request = Request(f'http://127.0.0.1:{server.server_port}/api/research', headers={'Host': 'flyhigh.fun'})
                with urlopen(request, timeout=5) as response:
                    payload = json.load(response)
            charted = [t for t in payload['tokens'] if t.get('candles')]
            self.assertEqual(len(charted), 1)
            self.assertEqual(charted[0]['token'], mh.SOURCE['token'])
            self.assertEqual(len(charted[0]['candles']), len(mh.load(verify_raw=False)['bars']))
            self.assertNotIn('raw_sources', charted[0])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_failed_refresh_preserves_snapshot_and_waits(self):
        stop = threading.Event()
        original = (mh.DEFAULT_DIR / 'copy.latest.json').read_bytes()
        def wait(seconds):
            self.assertEqual(seconds, 900)
            stop.set()
        with patch('flyhigh.market_history.refresh', side_effect=OSError('offline')) as fetch, patch.object(stop, 'wait', side_effect=wait):
            refresh_market(stop)
        fetch.assert_called_once_with(window_count=250)
        self.assertEqual(original, (mh.DEFAULT_DIR / 'copy.latest.json').read_bytes())

    def test_frontend_real_series_gap_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        script = """
const assert = require('node:assert/strict');
const ui = require('./web/research.js');
const data = require('./data/market-history/copy.latest.json');
const candles = ui.candlesOf({candles:data.bars.map(b=>({ts:b.timestamp,close:b.close}))});
const segments = ui.candleSegments(candles);
assert.equal(segments.length, data.quality.gaps_over_300_seconds + 1);
assert.equal(segments.flat().length, data.bars.length);
for (const s of segments) for(let i=1;i<s.length;i++) assert(s[i].ts-s[i-1].ts<=300000);
assert(ui.priceUSD(candles[0].close).startsWith('$'));
assert.equal(ui.candleSegments([{ts:0},{ts:300000},{ts:600001}]).length,2);
"""
        subprocess.run(['node', '-e', script], cwd=root, check=True)
