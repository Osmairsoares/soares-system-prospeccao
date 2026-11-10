"""Soares System - servidor e proxy OSM com fallback e diagnosticos."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit
from urllib.error import HTTPError, URLError
from pathlib import Path
import os, json, time, threading, hashlib, socket

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get('PORT', '10000'))
OVERPASS = ['overpass.private.coffee', 'overpass-api.de', 'overpass.kumi.systems', 'overpass.nchc.org.tw']
ALLOWED = {
    'nominatim.openstreetmap.org': ('/search',),
    'photon.komoot.io': ('/api/',),
    **{host: ('/api/interpreter',) for host in OVERPASS},
}
CALLS = {}
CACHE = {}
LOCK = threading.Lock()
MAX_RESPONSE = 12_000_000

def allowed(url):
    p = urlsplit(url)
    return (p.scheme == 'https' and p.hostname in ALLOWED and p.path in ALLOWED[p.hostname]
            and p.port in (None, 443) and not p.username and not p.password and not p.fragment)

def request_json(url, method, body, timeout=16):
    headers = {'User-Agent': 'SoaresSystem-Prospecao/2.0 (OSM community data; low-volume usage)',
               'Accept': 'application/json', 'Accept-Language': 'pt-BR',
               'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'}
    req = Request(url, data=body.encode('utf-8') if method == 'POST' else None,
                  headers=headers, method=method)
    with urlopen(req, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise ValueError('Resposta excedeu 12 MB')
    return json.loads(raw)

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        try: self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self.reply(200, {'ok': True, 'service': 'Soares System', 'version': '2.0'})
        if path == '/api/diagnostico':
            return self.reply(200, {'ok': True, 'version': '2.0', 'message': 'Servidor ativo. Disponibilidade dos serviços externos não garantida.'})
        if path not in ('/', '/Soares_System.html'):
            return self.send_error(404)
        file = ROOT / 'Soares_System.html'
        if not file.is_file():
            return self.reply(500, {'error': 'Arquivo Soares_System.html não encontrado no repositório'})
        body = file.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if urlsplit(self.path).path != '/api/proxy':
            return self.send_error(404)
        origin, host = self.headers.get('Origin', ''), self.headers.get('Host', '')
        if origin and urlsplit(origin).netloc != host:
            return self.reply(403, {'error': 'Origem não autorizada'})
        client = self.client_address[0]
        now = time.monotonic()
        with LOCK:
            recent = [t for t in CALLS.get(client, []) if now - t < 60]
            if len(recent) >= 18:
                return self.reply(429, {'error': 'Muitas consultas. Aguarde um minuto.'})
            recent.append(now)
            CALLS[client] = recent
            if len(CALLS) > 2000: CALLS.clear()
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 2 <= length <= 100000:
                return self.reply(413, {'error': 'Consulta muito grande ou vazia'})
            obj = json.loads(self.rfile.read(length))
            url = obj.get('url', '')
            if not isinstance(url, str) or not allowed(url):
                return self.reply(400, {'error': 'Destino não autorizado'})
            method = obj.get('method', 'GET').upper()
            if method not in ('GET', 'POST'):
                return self.reply(400, {'error': 'Método inválido'})
            body = obj.get('body', '')
            if not isinstance(body, str) or len(body) > 10000:
                return self.reply(400, {'error': 'Corpo inválido'})
            p = urlsplit(url)
            # Overpass pode receber a query no parametro data ou no corpo POST.
            query = parse_qs(p.query).get('data', [''])[0] or body
            is_overpass = p.hostname in OVERPASS
            if is_overpass and (not query or len(query) > 10000):
                return self.reply(400, {'error': 'Consulta Overpass ausente ou grande demais'})
            key = hashlib.sha256((('overpass:' + query) if is_overpass else (method + url + body)).encode()).hexdigest()
            with LOCK:
                entry = CACHE.get(key)
                if entry and entry[0] > time.monotonic():
                    print('CACHE HIT', p.hostname, flush=True)
                    return self.reply(200, entry[1])
            candidates = []
            if is_overpass:
                # Alterna os provedores sem mudar a interface nem o formato de resposta.
                for host_name in [p.hostname] + [h for h in OVERPASS if h != p.hostname]:
                    candidates.append(('https://' + host_name + '/api/interpreter', 'POST', 'data=' + urlencode({'data': query})[5:]))
            else:
                candidates.append((url, method, body))
            errors = []
            for target, verb, payload in candidates:
                hostname = urlsplit(target).hostname
                try:
                    print('CONSULTA', hostname, 'inicio', flush=True)
                    result = request_json(target, verb, payload, timeout=14 if is_overpass else 18)
                    with LOCK:
                        if len(CACHE) > 100: CACHE.clear()
                        CACHE[key] = (time.monotonic() + (1800 if is_overpass else 3600), result)
                    print('CONSULTA', hostname, 'sucesso', len(result.get('elements', [])) if isinstance(result, dict) else '', flush=True)
                    return self.reply(200, result)
                except (HTTPError, URLError, TimeoutError, socket.timeout, ValueError, OSError, json.JSONDecodeError) as exc:
                    detail = f'{hostname}: {type(exc).__name__} {str(exc)[:100]}'
                    print('CONSULTA FALHOU', detail, flush=True)
                    errors.append(detail)
            return self.reply(502, {'error': 'Serviços externos indisponíveis. ' + ' | '.join(errors)[:450]})
        except Exception as exc:
            print('ERRO PROXY', repr(exc), flush=True)
            return self.reply(502, {'error': f'Falha no servidor: {str(exc)[:200]}'})

    def log_message(self, fmt, *args):
        print('%s %s' % (self.address_string(), fmt % args), flush=True)

if __name__ == '__main__':
    print(f'Soares System v2.0 iniciado na porta {PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
