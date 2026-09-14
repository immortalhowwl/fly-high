import json
import threading
import unittest
from urllib.request import Request, urlopen
from flyhigh.server import make_server

class ResearchHTTPTests(unittest.TestCase):
    def test_public_dto_not_raw_envelope(self):
        server = make_server(0, public=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}/api/research'
            with urlopen(Request(url, headers={'Host': 'flyhigh.fun'}), timeout=5) as response:
                self.assertEqual(response.status, 200)
                payload = json.load(response)
            for field in ('as_of', 'wallets', 'fills', 'tokens', 'coverage'):
                self.assertIn(field, payload)
            self.assertNotIn('raw', payload)
            self.assertNotIn('payload', payload)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
