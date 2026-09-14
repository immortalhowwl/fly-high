import json
import threading
import unittest
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from flyhigh.server import make_server

class ServerTests(unittest.TestCase):
    def test_state_controls_and_origin(self):
        server=make_server(port=0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base+'/api/state') as r: state=json.load(r)
            self.assertEqual(state['report']['execution'],'simulated')
            with urlopen(base+'/') as r: self.assertIn(b'FLY HIGH',r.read())
            req=Request(base+'/api/control',data=b'{"action":"run"}',headers={'Content-Type':'application/json'})
            with urlopen(req) as r: self.assertTrue(json.load(r)['running'])
            bad=Request(base+'/api/control',data=b'{"action":"reset"}',headers={'Origin':'https://evil.test','Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as error: urlopen(bad)
            self.assertEqual(error.exception.code,403)
            with self.assertRaises(HTTPError): urlopen(base+'/../README.md')
        finally: server.shutdown(); server.server_close()
