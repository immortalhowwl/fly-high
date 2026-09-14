import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from flyhigh.server import make_server


class WalletReplayHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'wallet-seeded.report.json'
        self.server = make_server(0, report={'split': 1, 'generations': [], 'events': []}, directory=self.tmp.name)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def get(self):
        try:
            response = urlopen(f'http://127.0.0.1:{self.server.server_port}/api/wallet-replay')
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_blocked_envelope_preserved_without_evolution(self):
        envelope = {'status': 'blocked', 'seed_count': 0, 'replay': None, 'blocked_reasons': ['Insufficient cash evidence'], 'mappings': [], 'inputs': {'audit': 'digest'}}
        self.path.write_text(json.dumps(envelope))
        with patch('flyhigh.server.evolve', side_effect=AssertionError('read only')):
            self.assertEqual(self.get(), (200, envelope))

    def test_completed_envelope_preserved(self):
        envelope = {'status': 'completed', 'seed_count': 1, 'replay': {'split': 1, 'generations': [{'flies': []}]}, 'mappings': [{'admitted': True}]}
        self.path.write_text(json.dumps(envelope))
        self.assertEqual(self.get(), (200, envelope))

    def test_missing_and_corrupt_explicitly_unavailable(self):
        for content in (None, '{bad', '[]', '{"status":"completed","seed_count":0,"replay":null}', '{"status":"blocked","seed_count":0,"replay":null,"x":NaN}'):
            with self.subTest(content=content):
                if content is not None:
                    self.path.write_text(content)
                status, body = self.get()
                self.assertEqual(status, 503)
                self.assertEqual(body['status'], 'unavailable')
                self.assertEqual(body['seed_count'], 0)
                self.assertIsNone(body['replay'])
                self.assertTrue(body['blocked_reasons'])
