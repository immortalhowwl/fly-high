"""Synthetic fixtures test ingestion, never used as production research data."""
import unittest
from flyhigh import research

A = '0x' + 'a' * 40
T = '0x' + 'b' * 40
TX = '0x' + 'c' * 64


def captures():
    data = {
        'traders': [dict(address=A, handle='fixture-only', realized_pnl=1,
                         unrealized_pnl=None, net_pnl=1, fills=100, win_rate=None)],
        'tape': [dict(id=1, ts=100, tx=TX, wallet=A.upper().replace('0X', '0x'),
                      token=T, side='buy', usd=10, amount=2, symbol='TEST'),
                 dict(id=2, ts=100, tx=TX, wallet=A, token=T, side='sell',
                      usd=None, amount=None, symbol='TEST')],
        'closed': [], 'tokens': [dict(token=T, symbol='TEST', drained=True)],
        'status': {'chain_id': 4663}}
    return {key: dict(url='https://example.org/' + key, fetched_at='2026-09-14T00:00:00Z',
                      http_status=200, data=value) for key, value in data.items()}


class NormalizeTests(unittest.TestCase):
    def test_preserves_source_values_ids_and_missingness(self):
        raw = captures()
        raw['tape']['data'].append(dict(raw['tape']['data'][0]))
        dto = research.build_payload(raw)
        self.assertEqual(len(dto['fills']), 2)  # Same tx is NOT same event.
        self.assertEqual(dto['fills'][0]['wallet'], A)
        self.assertIsNone(dto['fills'][1]['usd'])
        self.assertIsNone(dto['wallets'][0]['unrealized_pnl'])
        self.assertEqual(dto['wallets'][0]['fills'], 100)
        self.assertNotIn('score', dto['wallets'][0])
        self.assertFalse(dto['coverage']['complete_history'])
        self.assertEqual(dto['wallets'][0]['rules']['status'], 'insufficient_history')
        self.assertEqual(dto['wallets'][0]['rules']['mapped_genes'], {})
        self.assertEqual(set(dto), {'as_of', 'source', 'window', 'coverage', 'wallets',
                                    'fills', 'tokens', 'metrics', 'warnings'})


class PersistenceTests(unittest.TestCase):
    def test_refresh_persists_raw_and_cache_survives_network_failure(self):
        from pathlib import Path
        import tempfile
        import json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'snapshot.json'
            with patch.object(research.TrenchesClient, 'fetch', side_effect=lambda key: captures()[key]):
                result = research.refresh_snapshot(path)
            self.assertEqual(research.load_snapshot(path), result)
            stored = json.loads(path.read_text())
            self.assertEqual(stored['raw']['traders']['data'][0]['handle'], 'fixture-only')
            with patch.object(research.TrenchesClient, 'fetch', side_effect=OSError('offline')):
                stale = research.refresh_snapshot(path)
            self.assertEqual(stale['as_of'], result['as_of'])
            self.assertTrue(stale['coverage']['endpoints']['traders']['stale'])
            self.assertTrue(any('offline' in w for w in stale['warnings']))
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_missing_cache_is_explicit_empty_payload(self):
        result = research.load_snapshot('/root/projects/fly-high/nonexistent-test-snapshot.json')
        self.assertEqual(result['wallets'], [])
        self.assertIsNone(result['as_of'])
        self.assertTrue(result['coverage']['missing_endpoints'])

    def test_client_retries_and_caches_with_timeout(self):
        from unittest.mock import patch
        import io
        response = io.BytesIO(b'[]')
        response.status = 200
        client = research.TrenchesClient(timeout=1, retries=1, cache_ttl=60)
        with patch.object(research, 'urlopen', side_effect=[OSError('timeout'), response]) as open_url:
            with patch.object(research.time, 'sleep'):
                first = client.fetch('traders')
                self.assertEqual(first, client.fetch('traders'))
                self.assertEqual(open_url.call_count, 2)
                self.assertEqual(open_url.call_args.kwargs['timeout'], 1)
        self.assertEqual(first['data'], [])
        self.assertIn('stocks=false', first['url'])


if __name__ == '__main__':
    unittest.main()
