import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from flyhigh.server import make_server


class HypothesisHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'hypothesis-replay.report.json'
        self.server = make_server(0, report={'split': 1, 'generations': [], 'events': []}, directory=self.tmp.name)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def get(self):
        try:
            response = urlopen(f'http://127.0.0.1:{self.server.server_port}/api/hypothesis-replay')
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_completed_readonly_preserves_full_envelope(self):
        envelope = {'status': 'completed', 'evaluation_kind': 'retrospective', 'seed_count': 1,
                    'replay': {'split': 1, 'generations': [{'flies': [{'seed_origin': {'provenance': {'wallet': 'a'}}}]}]},
                    'limits': ['Not forward validation'], 'overlap_note': 'Evidence overlaps final segment'}
        self.path.write_text(json.dumps(envelope))
        with patch('flyhigh.server.evolve', side_effect=AssertionError('read only')), patch('urllib.request.urlopen', side_effect=AssertionError('no upstream network')):
            self.assertEqual(self.get(), (200, envelope))

    def test_producer_experiment_kind_normalized_without_losing_receipts(self):
        envelope = {'status': 'completed', 'experiment_kind': 'retrospective_wallet_inspired_hypothesis',
                    'seed_count': 1, 'replay': {'split': 1, 'generations': [{'flies': [{'seed_origin': {'provenance': {'wallet': 'a'}}}]}]},
                    'limits': ['Evidence overlaps evaluation'], 'inputs': {'digest': 'receipt'}}
        self.path.write_text(json.dumps(envelope))
        status, body = self.get()
        self.assertEqual(status, 200)
        self.assertEqual(body['evaluation_kind'], 'retrospective')
        self.assertEqual(body['overlap_note'], envelope['limits'][0])
        self.assertEqual(body['inputs'], envelope['inputs'])

    def test_blocked_never_substitutes_archive(self):
        envelope = {'status': 'blocked', 'seed_count': 0, 'replay': None, 'blocked_reasons': ['No matching window']}
        self.path.write_text(json.dumps(envelope))
        self.assertEqual(self.get(), (200, envelope))

    def test_missing_corrupt_invalid_are_unavailable(self):
        for content in (None, '{bad', '[]', '{"status":"completed","seed_count":0,"replay":null}',
                        '{"status":"blocked","seed_count":0,"replay":null,"x":NaN}',
                        '{"status":"completed","evaluation_kind":"retrospective","seed_count":1,"replay":{"split":1,"generations":[{"flies":[]}]}}'):
            with self.subTest(content=content):
                if content is not None:
                    self.path.write_text(content)
                status, body = self.get()
                self.assertEqual(status, 503)
                self.assertEqual(body['status'], 'unavailable')
                self.assertEqual(body['seed_count'], 0)
                self.assertIsNone(body['replay'])
                self.assertTrue(body['blocked_reasons'])
