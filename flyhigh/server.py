"""Local research lab or explicit read-only public historical replay."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
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


def make_server(port=8765, report=None, directory=None, public=False):
    if public and report is None:
        report=json.loads((ROOT/'examples/copy.report.json').read_text())
    hosts=set(filter(None, (h.strip() for h in os.environ.get('FLYHIGH_ALLOWED_HOSTS','flyhigh.fun').split(','))))
    railway=os.environ.get('RAILWAY_PUBLIC_DOMAIN','').strip()
    if railway: hosts.add(railway)
    lab=Lab(report or evolve(synthetic()),directory or ROOT/'data')
    class Handler(BaseHTTPRequestHandler):
        timeout=10
        def log_message(self,*args): pass
        def send(self,status,body,ctype='application/json'):
            if not isinstance(body,bytes): body=json.dumps(body,allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',ctype)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','same-origin')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers(); self.wfile.write(body)
        def allowed(self):
            host=self.headers.get('Host','')
            if len(self.headers.get_all('Host',[])) != 1: return False
            if public: return host in hosts
            return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.allowed(): self.send(403,{'error':'allowed Host required'}); return
            path=urlsplit(self.path).path
            if path=='/api/state':
                state=({'public':True,'running':False,'cursor':0,'report':lab.report,
                        'collector':{'status':'disabled_public_replay','rows':[],'verified_pairs':0,'fresh':False}}
                       if public else lab.state())
                if urlsplit(self.path).query=='brief=1': state.pop('report',None)
                self.send(200,state)
            elif path=='/api/wallet-replay':
                try:
                    envelope=json.loads((lab.directory/'wallet-seeded.report.json').read_text())
                    if not isinstance(envelope,dict) or envelope.get('status') not in ('blocked','completed'):
                        raise ValueError('invalid envelope')
                    count=envelope.get('seed_count')
                    if type(count) is not int or count < 0:
                        raise ValueError('invalid seed count')
                    if envelope['status']=='completed' and (count < 1 or not isinstance(envelope.get('replay'),dict) or not envelope['replay'].get('generations') or envelope['replay'].get('split',0) < 1):
                        raise ValueError('invalid completed replay')
                    if envelope['status']=='blocked' and (count != 0 or envelope.get('replay') is not None):
                        raise ValueError('invalid blocked replay')
                    json.dumps(envelope,allow_nan=False)
                except (OSError,ValueError,TypeError):
                    self.send(503,{'status':'unavailable','seed_count':0,'replay':None,
                                   'blocked_reasons':['Precomputed wallet replay is missing or invalid.']})
                else: self.send(200,envelope)
            elif path=='/api/hypothesis-replay':
                # Persisted retrospective experiment only: no network, seed export or evolution.
                try:
                    envelope=json.loads((lab.directory/'hypothesis-replay.report.json').read_text())
                    if isinstance(envelope,dict) and envelope.get('experiment_kind') == 'retrospective_wallet_inspired_hypothesis':
                        envelope.setdefault('evaluation_kind','retrospective')
                        envelope.setdefault('overlap_note',' '.join(note for note in envelope.get('limits',[]) if isinstance(note,str) and 'overlap' in note.lower()))
                    if not isinstance(envelope,dict) or envelope.get('status') not in ('blocked','completed'):
                        raise ValueError('invalid envelope')
                    count=envelope.get('seed_count')
                    replay=envelope.get('replay')
                    if type(count) is not int or count < 0:
                        raise ValueError('invalid seed count')
                    if envelope['status']=='completed':
                        if envelope.get('evaluation_kind') != 'retrospective' or count < 1 or not isinstance(replay,dict):
                            raise ValueError('invalid retrospective replay')
                        generations=replay.get('generations')
                        if not isinstance(generations,list) or not generations or type(replay.get('split')) is not int or replay['split'] < 1:
                            raise ValueError('empty replay')
                        founders=generations[0].get('flies',[])
                        admitted=[f for f in founders if isinstance(f,dict) and isinstance(f.get('seed_origin'),dict) and f['seed_origin'].get('provenance',{}).get('wallet')]
                        if len(admitted) != count:
                            raise ValueError('founder count mismatch')
                    elif count != 0 or replay is not None:
                        raise ValueError('invalid blocked replay')
                    json.dumps(envelope,allow_nan=False)
                except (OSError,ValueError,TypeError,AttributeError,KeyError):
                    self.send(503,{'status':'unavailable','evaluation_kind':'retrospective','seed_count':0,'replay':None,
                                   'blocked_reasons':['Precomputed hypothesis replay is missing or invalid.']})
                else: self.send(200,envelope)
            elif path=='/api/behavior':
                # Pure derivation from the persisted envelope, including raw attribution.
                # Never acquire prices, export seeds, or evaluate a replay on this route.
                try:
                    from dataclasses import asdict
                    from .behavior_candidates import build_behavior_candidates
                    from .engine import Genome
                    snapshot=json.loads((lab.directory/'research.snapshot.json').read_text())
                    behavior=build_behavior_candidates(snapshot)
                    behavior['default_genome']=asdict(Genome())
                    behavior['integration_status']='awaiting_matching_market_window'
                    self.send(200,behavior)
                except (OSError,ValueError,TypeError,AttributeError,KeyError):
                    self.send(503,{'status':'unavailable','wallets':[],'candidates':[],
                                   'error':'Cached behavior evidence is missing or invalid.'})
            elif path=='/api/report': self.send(200,lab.report)
            elif path=='/api/events': self.send(200,lab.report['events'])
            elif path=='/healthz': self.send(200,{'status':'ok'})
            elif path=='/api/research':
                try:
                    from .research import load_snapshot
                    snapshot=load_snapshot()
                    self.send(200,snapshot)
                except (OSError,ValueError):
                    self.send(503,{'error':'Research snapshot is not available yet'})
            elif path=='/fly-hero.mp4':
                import re
                asset=WEB/'fly-hero.mp4'
                size=asset.stat().st_size
                start,end=0,size-1
                requested=self.headers.get('Range')
                if requested:
                    match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
                    if not match or not any(match.groups()):
                        self.send(416,{'error':'invalid range'}); return
                    a,b=match.groups()
                    if a:
                        start=int(a); end=min(int(b),size-1) if b else size-1
                    else:
                        start=max(0,size-int(b))
                    if start>end or start>=size:
                        self.send(416,{'error':'unsatisfiable range'}); return
                self.send_response(206 if requested else 200)
                self.send_header('Content-Type','video/mp4')
                self.send_header('Accept-Ranges','bytes')
                self.send_header('Content-Length',str(end-start+1))
                if requested: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.end_headers()
                with asset.open('rb') as stream:
                    stream.seek(start)
                    remaining=end-start+1
                    try:
                        while remaining:
                            chunk=stream.read(min(65536,remaining))
                            if not chunk: break
                            self.wfile.write(chunk); remaining-=len(chunk)
                    except (BrokenPipeError,ConnectionResetError): pass
            elif path in ('/','/research','/app.js','/motion.js','/playback.js','/code-background.js','/brand.css','/favicon.ico','/fly-icon.png','/apple-touch-icon.png','/hero.js','/hero.css','/fly-hero.jpg','/style.css','/research.js','/research.css'):
                name={'/':'index.html','/research':'research.html'}.get(path,path[1:])
                types={'.png':'image/png','.ico':'image/x-icon','.jpg':'image/jpeg','.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}
                self.send(200,(WEB/name).read_bytes(),types[Path(name).suffix])
            else: self.send(404,{'error':'not found'})
        def do_POST(self):
            origin=self.headers.get('Origin')
            expected=('https://' if public else 'http://')+self.headers.get('Host','')
            if not self.allowed() or (public and origin != expected) or (origin and origin != expected):
                self.send(403,{'error':'same origin required'}); return
            if public:
                self.send(405,{'error':'public replay controls run only in your browser'}); return
            if self.path!='/api/control': self.send(404,{'error':'not found'}); return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                self.send(415,{'error':'application/json required'}); return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 1024: raise ValueError('invalid body length')
                payload=json.loads(self.rfile.read(length))
                self.send(200,lab.control(payload['action']))
            except (ValueError,KeyError,TypeError) as exc: self.send(400,{'error':str(exc)})
    server=ThreadingHTTPServer(('0.0.0.0' if public else '127.0.0.1',port),Handler)
    server.lab=lab
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8765')))
    parser.add_argument('--public',action='store_true',help='read-only public archive; bind all interfaces; browser-local playback')
    parser.add_argument('--input',help='explicit CSV/JSON observed series; no synthetic fallback')
    parser.add_argument('--load-report',help='replay an existing generated report without rerunning selection or holdout')
    parser.add_argument('--seed',type=int,default=17)
    parser.add_argument('--max-gap',type=int,default=180,help='largest allowed gap between observed samples in seconds; 300 for contiguous five-minute closes')
    parser.add_argument('--report',help='write deterministic report JSON')
    parser.add_argument('--no-server',action='store_true')
    args=parser.parse_args()
    if args.public and not args.load_report and not args.input:
        args.load_report=str(ROOT/'examples/copy.report.json')
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
        server=make_server(args.port,report,public=args.public)
        refresh_stop=threading.Event()
        if args.public:
            def refresh_research():
                from .research import refresh_snapshot
                while not refresh_stop.is_set():
                    try: refresh_snapshot()
                    except Exception as exc: print(f'Research refresh unavailable: {type(exc).__name__}',flush=True)
                    refresh_stop.wait(900)
            threading.Thread(target=refresh_research,daemon=True).start()
        print(f'FLY HIGH {"public historical replay" if args.public else "local lab"} port {server.server_port}',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally:
            refresh_stop.set()
            server.server_close()

if __name__=='__main__': main()
