"""Public research must not be enriched with internal replay market history."""
import copy
import json
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.request import Request, urlopen

from flyhigh import market_history as mh
from flyhigh import server as app
from flyhigh.research import load_snapshot


class MarketIntegrationTests(unittest.TestCase):
    def get_research(self):
        server = app.make_server(0, public=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = Request(f'http://127.0.0.1:{server.server_port}/api/research',
                              headers={'Host': 'flyhigh.fun'})
            with urlopen(request, timeout=5) as response:
                return json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_real_http_returns_exact_upstream_without_extra_market_token(self):
        expected = load_snapshot()
        with patch('flyhigh.market_history.urlopen', side_effect=AssertionError('No market fetch')), \
             patch('flyhigh.research.urlopen', side_effect=AssertionError('No research fetch')):
            payload = self.get_research()
        self.assertEqual(payload, expected)
        self.assertEqual(len(payload['tokens']), len(expected['tokens']))

    def test_matching_token_keeps_upstream_candles_wallets_and_tape(self):
        snapshot = {'tokens': [{'token': mh.SOURCE['token'], 'chain': mh.SOURCE['chain'],
                                'candles': [{'ts': 123, 'close': 0.5}]}],
                    'wallets': [{'address': 'upstream-wallet'}],
                    'tape': [{'wallet': 'upstream-wallet', 'side': 'buy'}]}
        expected = copy.deepcopy(snapshot)
        with patch('flyhigh.research.load_snapshot', return_value=snapshot):
            payload = self.get_research()
        self.assertEqual(payload, expected)
        self.assertEqual(snapshot, expected)

    def test_public_startup_only_schedules_research_refresh(self):
        server = MagicMock()
        server.server_port = 8765
        with patch('sys.argv', ['flyhigh.server', '--public']), \
             patch.object(app, 'make_server', return_value=server), \
             patch.object(app.threading, 'Thread') as thread, \
             patch('flyhigh.market_history.refresh') as refresh:
            app.main()
        self.assertEqual(thread.call_count, 1)
        self.assertEqual(thread.call_args.kwargs['target'].__name__, 'refresh_research')
        thread.return_value.start.assert_called_once_with()
        refresh.assert_not_called()
        server.serve_forever.assert_called_once_with()
        server.server_close.assert_called_once_with()

    def test_market_history_remains_available_for_internal_replay(self):
        history = mh.load(verify_raw=False)
        self.assertTrue(history['bars'])
        self.assertEqual(history['token'], mh.SOURCE['token'])
