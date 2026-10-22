import json
import os
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    # Never forward the bearer token to a redirect target.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Firefly:
    def __init__(self):
        self.url = os.environ.get('FIREFLY_URL', '').rstrip('/')
        if self.url.endswith('/api/v1'):
            self.url = self.url[:-7]
        token_file = os.environ.get('FIREFLY_TOKEN_FILE')
        self.token = Path(token_file).read_text().strip() if token_file else os.environ.get('FIREFLY_TOKEN', '')
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, body=None, **params):
        if not self.url or not self.token:
            raise Problem('Set FIREFLY_URL and FIREFLY_TOKEN (or FIREFLY_TOKEN_FILE), then restart the sidecar.', 503)
        if urlsplit(self.url).scheme not in ('http', 'https'):
            raise Problem('FIREFLY_URL must use http:// or https://', 503)
        url = self.url + '/api/v1/' + path.lstrip('/')
        if params:
            url += '?' + urlencode({k: v for k, v in params.items() if v})
        req = Request(url, data=json.dumps(body).encode() if body is not None else None,
                      headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json',
                               'Content-Type': 'application/json', 'User-Agent': 'Firefly-Sidecar/0.1'}, method=method)
        try:
            with self.opener.open(req, timeout=25) as response:
                return json.load(response)
        except HTTPError as e:
            # Do not surface upstream content: it can contain secrets or HTML.
            raise Problem(f'Firefly returned HTTP {e.code} for {method} {path}. Check permissions, version and server logs.', 502) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise Problem('Unable to reach Firefly or read its JSON response. Check the server URL and network.', 502) from None

    def all(self, path, **params):
        result = []
        page = 1
        while True:
            response = self.request('GET', path, page=page, limit=100, **params)
            items = response['data']
            result.extend(items)
            pagination = response.get('meta', {}).get('pagination', {})
            # Some filtered endpoints report unfiltered totals. Stop at a short
            # page, using the server's page size in case it caps our limit.
            per_page = int(pagination.get('per_page') or 100)
            if not items or len(items) < per_page or page >= int(pagination.get('total_pages', 1)):
                return result
            page += 1
            if page > 10000:
                raise Problem('Firefly pagination exceeded the supported limit.', 502)

    def journal(self, journal_id):
        data = self.request('GET', 'transaction-journals/' + journal_id)['data']
        for split in data['attributes']['transactions']:
            if str(split['transaction_journal_id']) == journal_id:
                return data, split
        raise Problem('The selected split no longer exists. Refresh the list.', 409)
