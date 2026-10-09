"""Mint a short-lived chef-willie installation token.

The private key never lives in the repo. Set GITHUB_APP_PRIVATE_KEY to the PEM
(or its base64), or GITHUB_APP_PRIVATE_KEY_FILE to a PEM path. A token lasts
about an hour; callers mint a fresh one when the cache is near expiry.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

APP_ID = '5254425'
INSTALLATION_ID = '169706504'
BOT_NAME = 'chef-willie[bot]'
BOT_EMAIL = '340283198+chef-willie[bot]@users.noreply.github.com'
REPO = 'vanoostrum/librag'

_cached = None
_warned = False


def git_identity():
    return BOT_NAME, BOT_EMAIL


def private_key():
    raw = os.environ.get('GITHUB_APP_PRIVATE_KEY', '').strip()
    if not raw:
        path = os.environ.get('GITHUB_APP_PRIVATE_KEY_FILE', '').strip()
        if path:
            raw = open(path).read().strip()
    if not raw:
        return ''
    if not raw.startswith('-----'):
        raw = base64.b64decode(raw).decode().strip()
    return raw.replace('\\n', '\n') + '\n'


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def app_jwt(pem, now=None):
    now = int(time.time() if now is None else now)
    header = b64url(json.dumps({'alg': 'RS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    payload = b64url(json.dumps(
        {'iat': now - 60, 'exp': now + 540, 'iss': APP_ID}, separators=(',', ':')).encode())
    signing = f'{header}.{payload}'.encode()
    with tempfile.NamedTemporaryFile('w', delete=False) as handle:
        handle.write(pem)
        path = handle.name
    os.chmod(path, 0o600)
    try:
        sig = subprocess.run(
            ['openssl', 'dgst', '-sha256', '-sign', path],
            input=signing, check=True, capture_output=True).stdout
    finally:
        os.unlink(path)
    return f'{header}.{payload}.{b64url(sig)}'


def installation_token():
    """Return a ghs_ token, or None when no private key is configured."""
    global _cached, _warned
    if _cached and _cached[0] > time.time() + 60:
        return _cached[1]
    pem = private_key()
    if not pem:
        if not _warned:
            _warned = True
            print('GITHUB_APP_PRIVATE_KEY is unset; GitHub calls use the ambient login, not chef-willie[bot]',
                  file=sys.stderr)
        return None
    request = urllib.request.Request(
        f'https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens',
        data=b'',
        method='POST',
        headers={
            'Authorization': f'Bearer {app_jwt(pem)}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'librag-factory',
        },
    )
    with urllib.request.urlopen(request) as response:
        body = json.load(response)
    _cached = (time.time() + 45 * 60, body['token'])
    return body['token']
