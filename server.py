"""Soares System: hospedagem HTTP + proxy limitado para consultas OSM."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, parse_qs
from urllib.error import HTTPError, URLError
from pathlib import Path
import os, json, time, threading

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get('PORT', '10000'))
ALLOWED = {
    'nominatim.openstreetmap.org': ('/search',),
    'photon.komoot.io': ('/api/',),
    'overpass.private.coffee': ('/api/interpreter',),
    'overpass-api.de': ('/api/interpreter',),
}
# Limit requests per IP to reduce accidental overload of community APIs.
CALLS = {}
LOCK = threading.Lock()

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/health':
            return self.reply(200, {'ok': True, 'service': 'Soares System'})
        if self.path not in ('/', '/Soares_System.html'):
            return self.send_error(404)
        body = (ROOT / 'Soares_System.html').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/api/proxy':
            return self.send_error(404)
        # A same-origin guard, plus restricted destination allowlist.
        origin = self.headers.get('Origin', '')
        host = self.headers.get('Host', '')
        if origin and urlsplit(origin).netloc != host:
            return self.reply(403, {'error': 'Origem não autorizada'})
        client = self.client_address[0]
        now = time.monotonic()
        with LOCK:
            recent = [t for t in CALLS.get(client, []) if now - t < 60]
            if len(recent) >= 18:
                return self.reply(429, {'error': 'Muitas consultas. Aguarde um minuto e tente novamente.'})
            recent.append(now)
            CALLS[client] = recent
            if len(CALLS) > 2000:
                CALLS.clear()
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 2 or length > 100000:
                return self.reply(413, {'error': 'Consulta muito grande'})
            obj = json.loads(self.rfile.read(length))
            url = obj.get('url', '')
            parts = urlsplit(url)
            if (parts.scheme != 'https' or parts.hostname not in ALLOWED
                or parts.path not in ALLOWED.get(parts.hostname, ())
                or parts.port not in (None, 443) or parts.username or parts.password
                or parts.fragment):
                return self.reply(400, {'error': 'Servidor ou caminho não autorizado'})
            method = obj.get('method', 'GET').upper()
            if method not in ('GET', 'POST'):
                return self.reply(400, {'error': 'Método inválido'})
            body = obj.get('body', '')
            if not isinstance(body, str) or len(body) > 10000:
                return self.reply(400, {'error': 'Consulta inválida'})
            req = Request(url, data=body.encode() if method == 'POST' else None,
                headers={'User-Agent': 'SoaresSystem/1.0 (contact: admin of deployed instance)',
                         'Accept': 'application/json', 'Accept-Language': 'pt-BR',
                         'Content-Type': 'application/x-www-form-urlencoded'}, method=method)
            with urlopen(req, timeout=65) as res:
                raw = res.read(12000001)
                if len(raw) > 12000000:
                    raise ValueError('Resposta excedeu o limite de 12 MB')
            payload = json.loads(raw)
            return self.reply(200, payload)
        except HTTPError as e:
            return self.reply(502, {'error': f'Serviço externo retornou HTTP {e.code}'})
        except Exception as e:
            return self.reply(502, {'error': f'Falha na consulta externa: {str(e)[:240]}'})

    def log_message(self, fmt, *args):
        print('%s %s' % (self.address_string(), fmt % args), flush=True)

if __name__ == '__main__':
    print(f'Soares System iniciado na porta {PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
