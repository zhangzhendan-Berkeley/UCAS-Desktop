from __future__ import annotations
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
from urllib.parse import urlsplit
from .core import ROOT, DATA, read_json, write_json


class LocalAPI:
    """Read-only API v1. Attendance/enrollment is controlled by desktop jobs."""
    def __init__(self, store, lan=False, port=8765):
        token_path = DATA / 'api-token.txt'
        if not token_path.exists():
            token_path.write_text(secrets.token_urlsafe(32), encoding='ascii')
        self.token = token_path.read_text(encoding='ascii').strip()
        self.store = store
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, data, status=200, content_type='application/json; charset=utf-8'):
                if not isinstance(data, bytes):
                    data = json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Frame-Options', 'DENY')
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = urlsplit(self.path).path
                if path in ('/mobile/', '/mobile/index.html'):
                    self.send((ROOT / 'mobile/index.html').read_bytes(), content_type='text/html; charset=utf-8')
                    return
                if path == '/mobile/manifest.webmanifest':
                    self.send((ROOT / 'mobile/manifest.webmanifest').read_bytes(), content_type='application/manifest+json')
                    return
                if path == '/v1/health':
                    self.send({'app': 'UCAS Desktop', 'version': '0.1.0', 'api_version': 1})
                    return
                supplied = self.headers.get('Authorization', '')
                if not hmac.compare_digest(supplied, 'Bearer ' + owner.token):
                    self.send({'error': '需要有效的 Bearer Token'}, 401)
                    return
                if path == '/v1/modules':
                    self.send(read_json(ROOT / 'modules.json', []))
                elif path == '/v1/jobs':
                    self.send([{k: v for k, v in item.items() if k != 'log'} for item in owner.store.list()])
                else:
                    self.send({'error': '接口不存在'}, 404)

            def do_POST(self):
                self.send({'error': 'API v1 是只读接口；请通过桌面界面建立或停止任务。'}, 405)

        self.server = ThreadingHTTPServer(('0.0.0.0' if lan else '127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
