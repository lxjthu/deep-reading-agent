"""Optional external connections; no implicit credential or network reads."""
from __future__ import annotations
import json
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


def search_links(query, provider='cnki'):
    if not query.strip(): raise ValueError('Search query is required')
    roots = {'cnki': ('https://kns.cnki.net/kns8s/defaultresult/index', 'kw'), 'wos': ('https://www.webofscience.com/wos/woscc/basic-search', None), 'fulltext': ('https://scholar.google.com/scholar', 'q'), 'crossref': ('https://search.crossref.org/', 'q')}
    if provider not in roots: raise ValueError('Unknown retrieval provider')
    base, key = roots[provider]
    return {'provider': provider, 'query': query, 'url': base + ('?' + urlencode({key: query}) if key else ''), 'status': 'search_entry_only', 'retrieved': False, 'warnings': ['Browser login/subscription may be required. No search results or full text have been retrieved.']}


def request_online(base_url, path, method='GET', token=None, body=None, allow_write=False, params=None):
    parsed = urlsplit(base_url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username: raise ValueError('Invalid server URL')
    if not path.startswith('/api/') or '..' in path or '://' in path or '?' in path: raise ValueError('Expected a fixed /api/ endpoint path')
    method = method.upper()
    if method not in ('GET', 'HEAD') and not allow_write: raise ValueError('Online write requires explicit allow_write authorization')
    if token and parsed.scheme != 'https' and parsed.hostname not in ('localhost', '127.0.0.1'): raise ValueError('Remote credential transmission requires HTTPS')
    headers = {'Accept': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    data = None if body is None else json.dumps(body).encode('utf-8')
    if data is not None: headers['Content-Type'] = 'application/json'
    request = Request(base_url.rstrip('/') + path + ('?'+urlencode(params) if params else ''), data=data, headers=headers, method=method)
    # Refuse redirects rather than forwarding an authorization header elsewhere.
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
        payload = response.read(20 * 1024 * 1024 + 1)
        if len(payload) > 20 * 1024 * 1024: raise ValueError('Online response exceeds limit')
        return {'status': response.status, 'data': json.loads(payload), 'prompt_source': 'remote_effective_version_not_verified'}
