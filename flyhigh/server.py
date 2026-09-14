"""Loopback-only research server with a strict route allowlist."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
from .data import load, synthetic
from .engine import evolve

ROOT=Path(__file__).resolve().parent.parent
WEB=ROOT/'web'

class Lab:
    def __init__(self, report, directory):
        self.report=report
        self.directory=Path(directory)
        self.lock=threading.RLock()
        self.running=False
        self.cursor=0
        self.last=time.monotonic()

    def state(self):
        with self.lock:
            now=time.monotonic()
            length=self.report['split']*len(self.report['generations'])
            if self.running:
                self.cursor=min(length-1,self.cursor+(now-self.last)*20)
                if self.cursor>=length-1: self.running=False
            self.last=now
            try: source=json.loads((self.directory/'latest.json').read_text())
            except (OSError,ValueError): source={'status':'not_started','rows':[],'verified_pairs':0}
            source['fresh']=bool(source.get('rows')) and time.time()-source.get('observed_at',0)<180
            return {'running':self.running,'cursor':int(self.cursor),'report':self.report,'collector':source}

    def control(self,action):
        with self.lock:
            self.state()
            if action=='run': self.running=True
            elif action=='pause': self.running=False
            elif action=='reset': self.cursor=0; self.running=False
            elif action=='replay': self.cursor=0; self.running=True
            elif action=='generation': self.cursor=min(self.report['split']*len(self.report['generations'])-1,(int(self.cursor)//self.report['split']+1)*self.report['split'])
            else: raise ValueError('unknown action')
            return self.state()


def make_server(port=8765, report=None, directory=None):
    lab=Lab(report or evolve(synthetic()),directory or ROOT/'data')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,status,body,ctype='application/json'):
            if not isinstance(body,bytes): body=json.dumps(body,allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',ctype)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(body)
        def allowed(self):
            host=self.headers.get('Host','')
            return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.allowed(): self.send(403,{'error':'loopback Host required'}); return
            path=urlsplit(self.path).path
            if path=='/api/state':
                state=lab.state()
                if urlsplit(self.path).query=='brief=1': state.pop('report',None)
                self.send(200,state)
            elif path=='/api/report': self.send(200,lab.report)
            elif path=='/api/events': self.send(200,lab.report['events'])
            elif path in ('/','/app.js','/motion.js','/style.css'):
                name='index.html' if path=='/' else path[1:]
                types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}
                self.send(200,(WEB/name).read_bytes(),types[Path(name).suffix])
            else: self.send(404,{'error':'not found'})
        def do_POST(self):
            origin=self.headers.get('Origin')
            if not self.allowed() or (origin and origin != 'http://'+self.headers.get('Host','')):
                self.send(403,{'error':'same origin required'}); return
            if self.path!='/api/control': self.send(404,{'error':'not found'}); return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.send(415,{'error':'application/json required'}); return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 1024: raise ValueError('invalid body length')
                payload=json.loads(self.rfile.read(length))
                self.send(200,lab.control(payload['action']))
            except (ValueError,KeyError,TypeError) as exc: self.send(400,{'error':str(exc)})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.lab=lab
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--input',help='explicit CSV/JSON observed series; no synthetic fallback')
    parser.add_argument('--load-report',help='replay an existing generated report without rerunning selection or holdout')
    parser.add_argument('--seed',type=int,default=17)
    parser.add_argument('--max-gap',type=int,default=180,help='largest allowed gap between observed samples in seconds; 300 for contiguous five-minute closes')
    parser.add_argument('--report',help='write deterministic report JSON')
    parser.add_argument('--no-server',action='store_true')
    args=parser.parse_args()
    if args.load_report:
        if args.input: parser.error('--input and --load-report are mutually exclusive')
        report=json.loads(Path(args.load_report).read_text())
        if report.get('schema_version') != 1 or not report.get('generations') or report.get('split',0) < 1:
            parser.error('unsupported or empty report')
    else:
        report=evolve(load(args.input) if args.input else synthetic(),seed=args.seed,max_gap=args.max_gap)
        report['mode']='replay' if args.input else 'synthetic'
        report['source']=Path(args.input).name if args.input else 'seeded offline fixture; not market history'
    if args.report:
        path=Path(args.report); path.parent.mkdir(parents=True,exist_ok=True)
        events=path.with_suffix('.events.jsonl')
        if events.exists():
            # Never overwrite a previously published ledger.
            existing=events.read_text()
            expected=''.join(json.dumps(e,sort_keys=True)+'\n' for e in report['events'])
            if existing!=expected: raise ValueError('event ledger exists for a different run; choose a new report path')
        else:
            with events.open('x') as f:
                for event in report['events']: f.write(json.dumps(event,sort_keys=True)+'\n')
        path.write_text(json.dumps(report,indent=2,allow_nan=False))
        print(f'Report: {path}; events: {events}')
    print(json.dumps({'mode':report['mode'],'champion':report['champion']['id'],
                      'holdout_return':report['holdout']['return'],'baselines':{k:v['return'] for k,v in report['baselines'].items()}}))
    if not args.no_server:
        server=make_server(args.port,report)
        print(f'FLY HIGH http://127.0.0.1:{server.server_port}',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()

if __name__=='__main__': main()
