from __future__ import annotations
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse
from .prompt_loader import PACKAGE


class ConfigurationError(ValueError):
    pass


class RemoteError(RuntimeError):
    pass


def load_config(env_path=None):
    path = Path(env_path or PACKAGE / '.env').resolve()
    defaults = PACKAGE / '.env.example'
    values, sources = {}, {}
    for file in (defaults, path):
        if file.exists():
            for line in file.read_text(encoding='utf-8-sig').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('\"\'')
                sources[key.strip()] = 'sample' if file == defaults else 'explicit_env'
    for key in set(values) | {'MIMO_API_KEY', 'DEEPSEEK_API_KEY'}:
        if key in os.environ:
            values[key], sources[key] = os.environ[key], 'environment'
    for key in ('DRA_COMPARE_INPUT_DIR', 'DRA_COMPARE_OUTPUT_DIR'):
        if values.get(key):
            values[key] = str((path.parent / values[key]).resolve())
    return values, sources


class Client:
    def __init__(self, provider, config=None, env_path=None, transport=None):
        self.config, self.sources = load_config(env_path) if config is None else (config, {})
        self.provider = provider
        self.transport = transport
        if provider not in ('mimo', 'deepseek'):
            raise ConfigurationError('Native Codex requires a verified platform execution; no API emulation is allowed')
        prefix = provider.upper()
        self.key = self.config.get(prefix + '_API_KEY', '')
        if not self.key or len(self.key) < 20 or any(x in self.key.lower() for x in ('your-key', 'xxxx', '填写')):
            raise ConfigurationError(prefix + '_API_KEY missing or placeholder')
        if provider == 'mimo':
            mode = self.config.get('MIMO_API_MODE', 'auto')
            token = self.key.startswith('tp-') if mode == 'auto' else mode in ('token-plan', 'token_plan', 'token')
            self.base = self.config['MIMO_TOKEN_PLAN_BASE_URL' if token else 'MIMO_PAYG_BASE_URL']
        else:
            self.base = self.config['DEEPSEEK_BASE_URL']
        if urlparse(self.base).scheme != 'https':
            raise ConfigurationError('API base URL must use HTTPS')
        self.model = self.config[prefix + '_MODEL']
        self.retries = min(5, max(0, int(self.config.get('DRA_COMPARE_API_MAX_RETRIES', 1))))
        self.timeout = int(self.config.get('DRA_COMPARE_API_TIMEOUT_SECONDS', 180))
        self.max_tokens = int(self.config.get('DRA_COMPARE_API_MAX_OUTPUT_TOKENS', 8000))

    def public(self):
        return {'provider': self.provider, 'model': self.model, 'base_url': self.base, 'max_tokens': self.max_tokens, 'max_retries': self.retries, 'thinking':self.config.get('DRA_API_THINKING','disabled'), 'configuration_sources': self.sources}

    def complete(self, messages):
        import httpx
        start = time.monotonic()
        attempts = []
        for attempt in range(self.retries + 1):
            try:
                with httpx.Client(timeout=self.timeout, transport=self.transport, follow_redirects=False) as client:
                    payload={'model': self.model, 'messages': messages, 'max_tokens': self.max_tokens}
                    if self.config.get('DRA_API_THINKING','disabled') in ('enabled','disabled'):
                        payload['thinking']={'type':self.config.get('DRA_API_THINKING','disabled')}
                    response = client.post(self.base.rstrip('/') + '/chat/completions', headers={'Authorization': 'Bearer ' + self.key}, json=payload)
                if response.status_code >= 400:
                    retry = response.status_code == 429 or response.status_code >= 500
                    attempts.append({'attempt': attempt + 1, 'status_code': response.status_code})
                    if retry and attempt < self.retries:
                        time.sleep(min(2 ** attempt, 10))
                        continue
                    raise RemoteError(f'API HTTP {response.status_code}; response body withheld')
                data = response.json()
                choice = data['choices'][0]
                content = choice['message'].get('content')
                if not isinstance(content, str) or not content.strip():
                    raise RemoteError('API returned no text; '+json.dumps({'finish_reason':choice.get('finish_reason'),'model':data.get('model'),'usage':data.get('usage')},ensure_ascii=False))
                return {'content': content, 'provider': self.provider, 'model': data.get('model', self.model), 'usage': data.get('usage'), 'finish_reason': choice.get('finish_reason'), 'truncated': choice.get('finish_reason') == 'length', 'elapsed_seconds': time.monotonic()-start, 'attempts': attempts + [{'attempt': attempt + 1, 'status_code': 200}]}
            except (httpx.TimeoutException, httpx.TransportError):
                attempts.append({'attempt': attempt+1, 'error': 'transport_failure', 'remote_completion_uncertain': True})
                if attempt == self.retries:
                    raise RemoteError('Transport failure; remote completion and billing uncertain') from None
                time.sleep(min(2 ** attempt, 10))
            except (KeyError, ValueError, IndexError):
                raise RemoteError('Malformed API response; body withheld') from None
