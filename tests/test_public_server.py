import json
import os
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from flyhigh.server import make_server


class PublicServerTests(unittest.TestCase):
    def test_public_cli_defaults_to_archived_report(self):
        result=subprocess.run([sys.executable,'-m','flyhigh.server','--public','--no-server'],capture_output=True,text=True,timeout=15,env={**os.environ,'PORT':'9876'})
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['mode'],'historical_prices_assumed_liquidity')

    def test_public_is_read_only_and_exact_host_guarded(self):
        with patch.dict(os.environ, {'FLYHIGH_ALLOWED_HOSTS': 'flyhigh.fun', 'RAILWAY_PUBLIC_DOMAIN': 'demo.up.railway.app'}):
            server = make_server(port=0, public=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        def get(path, host='flyhigh.fun', **headers):
            return urlopen(Request(base+path, headers={'Host': host, **headers}), timeout=3)
        try:
            self.assertEqual(server.server_address[0], '0.0.0.0')
            with get('/api/state') as response:
                state = json.load(response)
            self.assertTrue(state['public'])
            self.assertEqual(state['report']['mode'], 'historical_prices_assumed_liquidity')
            self.assertEqual(state['collector']['status'], 'disabled_public_replay')
            with get('/healthz', host='demo.up.railway.app') as response:
                self.assertEqual(response.status, 200)
            for host in ['evil.test', 'flyhigh.fun.evil.test', 'flyhigh.fun:80', 'flyhigh.fun@evil.test']:
                with self.assertRaises(HTTPError) as error: get('/', host=host)
                self.assertEqual(error.exception.code, 403)
            for origin, status in [('https://flyhigh.fun',405), ('http://flyhigh.fun',403), ('https://evil.test',403), ('https://demo.up.railway.app',403), ('',403)]:
                request = Request(base+'/api/control', data=b'{"action":"run"}', headers={'Host':'flyhigh.fun','Origin':origin,'Content-Type':'application/json'})
                with self.assertRaises(HTTPError) as error: urlopen(request, timeout=3)
                self.assertEqual(error.exception.code,status)
            with get('/api/state?brief=1') as response:
                state=json.load(response)
                self.assertFalse(state['running'])
                self.assertEqual(state['cursor'],0)
                self.assertNotIn('report',state)
            self.assertFalse(server.lab.running)
        finally:
            server.shutdown()
            server.server_close()
