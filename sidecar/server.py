import base64
import hmac
import re
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .client import Firefly, Problem
from .store import Store
from .auditing import AuditedFirefly, activity_descriptions
from .tools import TOOLS
from .tools.reimbursements import Reimbursements
from .tools.validation import Validation
from .tools.duplicates import Duplicates
from .tools.gbit import GBIT
from .tools.consistency import Consistency

STATIC = Path(__file__).parent / 'static'


def make_handler(client=None, store=None):
    client = client or Firefly()
    store = store or Store(os.environ.get('DATA_DIR', './data') + '/sidecar.sqlite3')
    client = AuditedFirefly(client, store)
    tool = Reimbursements(client, store)
    duplicates = Duplicates(client)
    validation = Validation(client, tool.lock)
    gbit = GBIT(client,store,validation,tool.lock)
    consistency=Consistency(client,validation)
    csrf = secrets.token_urlsafe(32)
    hosts = os.environ.get('SIDECAR_HOSTS', 'localhost,127.0.0.1,[::1]').split(',')
    password = os.environ.get('SIDECAR_PASSWORD', '')
    username = os.environ.get('SIDECAR_USERNAME', 'sidecar')
    base_path = os.environ.get('SIDECAR_BASE_PATH', '').rstrip('/')
    if base_path and (not re.fullmatch(r'(?:/[A-Za-z0-9_-]+)+', base_path)):
        raise ValueError('SIDECAR_BASE_PATH must be a path such as /sidecar, or empty.')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Access log contains no bodies, query strings or credentials.
            print(f'{self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ""}', flush=True)

        def respond(self, status, payload, mime='application/json'):
            data = json.dumps(payload).encode() if mime == 'application/json' else payload
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'same-origin')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            try:
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                # The caller disconnected; never try to send another response.
                self.close_connection = True

        def allowed(self):
            host = self.headers.get('Host', '').lower()
            hostname = host.rsplit(':', 1)[0] if ':' in host and not host.endswith(']') else host
            if hostname not in [x.strip().lower() for x in hosts]:
                raise Problem('Host not allowed. Add your sidecar hostname to SIDECAR_HOSTS.', 403)
            if password:
                expected = 'Basic ' + base64.b64encode((username + ':' + password).encode()).decode()
                if not hmac.compare_digest(self.headers.get('Authorization', ''), expected):
                    self.send_response(401)
                    self.send_header('WWW-Authenticate', 'Basic realm="Firefly Sidecar"')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return False
            return True

        def route_path(self):
            path = urlsplit(self.path).path
            if base_path and path.startswith(base_path + '/'):
                return path[len(base_path):]
            # Also accept a proxy that strips the prefix before forwarding.
            return path

        def do_GET(self):
            try:
                raw_path = urlsplit(self.path).path
                path = self.route_path()
                if path == '/healthz':
                    return self.respond(200, {'status': 'ok'})
                if not self.allowed():
                    return
                if base_path and raw_path == base_path:
                    self.send_response(308)
                    self.send_header('Location', base_path + '/' + ('?' + urlsplit(self.path).query if urlsplit(self.path).query else ''))
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                query = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
                if path == '/api/bootstrap':
                    return self.respond(200, {'csrf': csrf, 'tools': TOOLS, 'configured': bool(client.url and client.token),
                                              'firefly_url': os.environ.get('FIREFLY_PUBLIC_URL', client.url),
                                              'firefly_public_url': os.environ.get('FIREFLY_PUBLIC_URL', ''), 'tag': tool.tag, 'todo_tag': validation.tag, 'mark_cash_remove_todo': validation.cash_remove_todo})
                if path == '/api/reimbursements':
                    from datetime import date
                    for key in ('start', 'end'):
                        if query.get(key):
                            date.fromisoformat(query[key])
                    return self.respond(200, tool.listing(query.get('start', ''), query.get('end', '')))
                if path == '/api/duplicates':
                    return self.respond(200, duplicates.listing(query.get('start', ''), query.get('end', ''), query.get('days', '3'), query.get('offset', '0')))
                if path == '/api/gbit':
                    return self.respond(200,gbit.listing(query.get('start',''),query.get('end','')))
                if path == '/api/consistency/status':
                    return self.respond(200,consistency.status(query.get('id','')))
                if path == '/api/consistency/results':
                    return self.respond(200,consistency.results(query.get('id',''),query.get('page','1'),query.get('limit','25'),query.get('show','inconsistent')))
                if path == '/api/consistency':
                    return self.respond(200,consistency.scan(query,full=True))
                if path == '/api/validation':
                    return self.respond(200, validation.listing())
                if path == '/api/activity':
                    from datetime import date
                    try:
                        offset=int(query.get('offset','0'));limit=int(query.get('limit','50'))
                    except ValueError:
                        raise Problem('Invalid activity pagination.') from None
                    if offset<0 or limit not in (25,50,100):raise Problem('Invalid activity pagination.')
                    state=query.get('state','');action=query.get('action','');gid=query.get('group_id','')
                    start=query.get('start','');end=query.get('end','')
                    if state not in ('','pending','completed','uncertain','blocked','review','partial'):raise Problem('Invalid activity outcome.')
                    if len(action)>200 or (gid and (not gid.isascii() or not gid.isdigit())):raise Problem('Invalid activity filter.')
                    try:
                        for value in (start,end):
                            if value and date.fromisoformat(value).isoformat()!=value:raise ValueError()
                        if start and end and start>end:raise ValueError()
                        if end=='9999-12-31':raise ValueError()
                    except ValueError:raise Problem('Choose a valid activity date range.') from None
                    return self.respond(200,activity_descriptions(client,store.events(offset,limit,state,action,gid,start,end)))
                if path == '/api/gbit/plan':
                    return self.respond(200,gbit.saved(query.get('plan_id','')))
                if path == '/api/reimbursements/plan':
                    plan_id=query.get('plan_id','')
                    if not plan_id or len(plan_id)>100:raise Problem('Invalid review ID.')
                    saved,_,_=store.get(plan_id)
                    deposit=saved['deposit']
                    if not deposit.get('group_id'):
                        parent,_=client.journal(str(deposit['transaction_journal_id']))
                        deposit['group_id']=str(parent['id'])
                    return self.respond(200,saved)
                if path == '/api/history':
                    history = store.history()
                    # Old saved plans predate parent IDs on deposit snapshots.
                    for entry in history:
                        deposit = entry['plan']['deposit']
                        if not deposit.get('group_id'):
                            try:
                                parent, _ = client.journal(str(deposit['transaction_journal_id']))
                                deposit['group_id'] = str(parent['id'])
                            except Problem:
                                pass  # Retain history even if its Firefly transaction was deleted.
                    return self.respond(200, history)
                if path == '/api/connection':
                    info = client.request('GET', 'about')['data']
                    return self.respond(200, {'connected': True, 'version': info.get('version', 'unknown')})
                if path == '/manifest.webmanifest':
                    root = base_path + '/'
                    manifest = {
                        'id': root, 'name': 'Firefly Sidecar', 'short_name': 'Sidecar',
                        'description': 'Review and organize your Firefly III transactions.',
                        'start_url': root, 'scope': root, 'display': 'standalone',
                        'background_color': '#f3f6f9', 'theme_color': '#263544',
                        'icons': [
                            {'src': root + 'icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
                            {'src': root + 'icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
                            {'src': root + 'icon-maskable-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
                        ],
                    }
                    return self.respond(200, json.dumps(manifest).encode(), 'application/manifest+json')
                assets = {'/sw.js': ('sw.js', 'text/javascript; charset=utf-8'),
                          '/pwa.js': ('pwa.js', 'text/javascript; charset=utf-8'),
                          '/offline.html': ('offline.html', 'text/html; charset=utf-8'),
                          '/icon-180.png': ('icon-180.png', 'image/png'),
                          '/icon-192.png': ('icon-192.png', 'image/png'),
                          '/icon-512.png': ('icon-512.png', 'image/png'),
                          '/icon-maskable-512.png': ('icon-maskable-512.png', 'image/png'),
                          '/': ('index.html', 'text/html; charset=utf-8'),
                          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                          '/style.css': ('style.css', 'text/css; charset=utf-8')}
                if path in assets:
                    filename, mime = assets[path]
                    content = (STATIC / filename).read_bytes()
                    if filename == 'index.html':
                        content = content.replace(b'__SIDECAR_BASE_PATH__', base_path.encode())
                    return self.respond(200, content, mime)
                raise Problem('Not found.', 404)
            except Problem as e:
                self.respond(e.status, {'error': str(e)})
            except ValueError:
                self.respond(400, {'error': 'Invalid date. Use YYYY-MM-DD.'})
            except Exception:
                self.respond(500, {'error': 'Unexpected server error. Check sidecar configuration and Firefly API compatibility.'})

        def do_POST(self):
            try:
                if not self.allowed():
                    return
                if not hmac.compare_digest(self.headers.get('X-Sidecar-CSRF', ''), csrf):
                    raise Problem('Session expired. Reload this page.', 403)
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise Problem('JSON required.', 415)
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536:
                    raise Problem('Invalid request size.', 413)
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise Problem('JSON object required.')
                path = self.route_path()
                if path == '/api/consistency/fix-preview':
                    return self.respond(200,consistency.fix_preview(body))
                if path == '/api/consistency/fix':
                    return self.respond(200,consistency.fix(body))
                if path == '/api/consistency/start':
                    return self.respond(200,consistency.start(body))
                if path == '/api/consistency/cancel':
                    return self.respond(200,consistency.cancel(body.get('id','')))
                if path == '/api/validation/categorize-options':
                    return self.respond(200,validation.categorize_options(body))
                if path == '/api/validation/categorize':
                    return self.respond(200,validation.categorize(body))
                if path == '/api/validation/mark-gbit':
                    return self.respond(200,gbit.flag(body))
                if path == '/api/gbit/review':
                    return self.respond(200,gbit.prepare(body))
                if path == '/api/gbit/apply':
                    return self.respond(200,gbit.apply(body))
                if path == '/api/validation/delete-preview':
                    return self.respond(200, validation.delete_preview(body))
                if path == '/api/validation/delete':
                    return self.respond(200, validation.delete(body))
                if path == '/api/validation/refund-candidates':
                    return self.respond(200, validation.refund_candidates(body))
                if path == '/api/validation/mark-refund':
                    return self.respond(200, validation.mark_refund(body))
                if path == '/api/validation/split-options':
                    return self.respond(200, validation.reimbursement_options(body))
                if path == '/api/validation/split':
                    return self.respond(200, validation.split_transaction(body))
                if path == '/api/validation/reimbursement-options':
                    return self.respond(200, validation.reimbursement_options(body))
                if path == '/api/validation/mark-reimbursement':
                    return self.respond(200, validation.mark_reimbursement(body))
                if path == '/api/validation/mark-cash':
                    return self.respond(200, validation.mark_cash(body))
                if path == '/api/validation/complete-group':
                    return self.respond(200, validation.complete_group(body))
                if path == '/api/validation/complete':
                    return self.respond(200, validation.complete(body))
                if path == '/api/reimbursements/review':
                    return self.respond(200, tool.prepare(body))
                if path == '/api/reimbursements/apply':
                    plan_id = body.get('plan_id')
                    if not isinstance(plan_id, str) or len(plan_id) > 100:
                        raise Problem('Invalid review ID.')
                    return self.respond(200, tool.apply(plan_id))
                raise Problem('Not found.', 404)
            except Problem as e:
                self.respond(e.status, {'error': str(e)})
            except (ValueError, TypeError):
                self.respond(400, {'error': 'Invalid JSON request.'})
            except Exception:
                self.respond(500, {'error': 'Unexpected error. Inspect History before retrying; an upstream write may have completed.'})
    return Handler


def main():
    os.umask(0o077)
    server = ThreadingHTTPServer((os.environ.get('BIND', '127.0.0.1'), int(os.environ.get('PORT', '8080'))), make_handler())
    print('Firefly Sidecar listening on port ' + str(server.server_port), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
