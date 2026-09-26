"""Loopback judge service: read artifacts and run the synthetic benchmark only."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ..runner import ROOT
from .runner import run


def handler_for(run_path):
    state={'path':run_path.resolve()}
    if not state['path'].is_relative_to((ROOT/'runs').resolve()):raise ValueError('run outside simulation')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass

        def send(self,status,body,content_type='application/json; charset=utf-8'):
            data=body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data)

        def do_GET(self):
            parsed=urlparse(self.path)
            files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if parsed.path in files:
                name,mime=files[parsed.path];self.send(200,(ROOT/'ui'/name).read_bytes(),mime);return
            if parsed.path=='/api/run':
                p=state['path']/'judge-data.json'
                if not p.exists():self.send(409,{'error':'Run has no judge evidence; inspect retained manifest.'});return
                self.send(200,p.read_bytes());return
            if parsed.path=='/api/artifact':
                relative=parse_qs(parsed.query).get('path',[''])[0]
                base=state['path'];p=(base/relative).resolve()
                if not relative or not p.is_relative_to(base) or not p.is_file() or p.suffix not in ('.json','.jsonl','.txt','.csv'):
                    self.send(404,{'error':'Artifact unavailable.'});return
                self.send(200,p.read_bytes(),'text/plain; charset=utf-8');return
            self.send(404,{'error':'Not found.'})

        def do_POST(self):
            expected=f'http://127.0.0.1:{self.server.server_port}'
            if self.headers.get('Origin') not in (None,expected) or self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':
                self.send(403,{'error':'Local origin required.'});return
            if self.path!='/api/reset-run':self.send(404,{'error':'Not found.'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length>1024:raise ValueError('size')
                args=json.loads(self.rfile.read(length) or b'{}')
                if args!={}:raise ValueError('unsupported configuration')
                prior=json.loads((state['path']/'manifest.json').read_text())
                path=run(preset=prior['preset'],seed=prior['seed'],cases=tuple(prior['cases']))
                state['path']=path
                self.send(200,{'run_id':path.name,'status':'SYNTHETIC_ONLY'})
            except (ValueError,OSError):self.send(400,{'error':'Cannot run; inspect retained artifacts.'})
    return Handler


def serve(run_path,port=8765):
    server=ThreadingHTTPServer(('127.0.0.1',port),handler_for(run_path))
    print(f'Judge replay: http://127.0.0.1:{server.server_port} — product NOT_RUN',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
