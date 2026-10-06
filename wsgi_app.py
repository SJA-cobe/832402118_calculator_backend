"""WSGI entry point reusing the calculator's existing API dispatcher."""
import json
import os
import sys
from email.message import Message
from http import HTTPStatus
from pathlib import Path

ROOT = Path(os.environ.get('CALCULATOR_ROOT', '/home/jssun/calculator'))
sys.path.insert(0, str(ROOT / 'backend' / 'src'))
from database import HistoryStore
from server import make_handler

store = HistoryStore(ROOT / 'backend' / 'data' / 'calculator.db')
BaseHandler = make_handler(store, [])


class WSGIRequest(BaseHandler):
    """Adapt WSGI input and output without opening a listening socket."""
    def __init__(self, environ):
        self.command = environ['REQUEST_METHOD']
        self.path = environ.get('PATH_INFO', '/')
        query = environ.get('QUERY_STRING', '')
        if query:
            self.path += '?' + query
        self.headers = Message()
        self.headers['Content-Type'] = environ.get('CONTENT_TYPE', '')
        self.headers['Content-Length'] = environ.get('CONTENT_LENGTH') or '0'
        self.rfile = environ['wsgi.input']
        self.status = 500
        self.body = b''

    def respond(self, status, data):
        self.status = status
        self.body = json.dumps(data, ensure_ascii=False).encode('utf-8')


def application(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    method = environ.get('REQUEST_METHOD', 'GET')
    content_type = 'application/json; charset=utf-8'
    if path.startswith('/api/'):
        if method == 'OPTIONS':
            start_response('204 No Content', [
                ('Allow', 'GET, POST, DELETE, OPTIONS'),
                ('Content-Length', '0'),
            ])
            return [b'']
        request = WSGIRequest(environ)
        request.dispatch()
        status, body = request.status, request.body
    else:
        files = {
            '/': ('index.html', 'text/html; charset=utf-8'),
            '/index.html': ('index.html', 'text/html; charset=utf-8'),
            '/style.css': ('style.css', 'text/css; charset=utf-8'),
            '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
            '/config.js': ('config.js', 'application/javascript; charset=utf-8'),
        }
        if path not in files:
            status, body = 404, b'{"success":false,"message":"Not found"}'
        elif method not in ('GET', 'HEAD'):
            status, body = 405, b'{"success":false,"message":"Method not allowed"}'
        else:
            filename, content_type = files[path]
            body = (ROOT / 'frontend' / 'src' / filename).read_bytes()
            status = 200
    start_response(f'{status} {HTTPStatus(status).phrase}', [
        ('Content-Type', content_type),
        ('Content-Length', str(len(body))),
        ('X-Content-Type-Options', 'nosniff'),
    ])
    return [b'' if method == 'HEAD' else body]
