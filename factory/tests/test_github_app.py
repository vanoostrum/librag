"""JWT signing for the factory GitHub App. No network."""

import base64
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import github_app


def _decode(part):
    return json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))


class GithubAppTests(unittest.TestCase):
    def test_missing_key_returns_no_token(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(github_app.private_key(), '')

    def test_base64_key_round_trips(self):
        pem = '-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n'
        encoded = base64.b64encode(pem.encode()).decode()
        with unittest.mock.patch.dict(os.environ, {'GITHUB_APP_PRIVATE_KEY': encoded}, clear=True):
            self.assertTrue(github_app.private_key().startswith('-----BEGIN PRIVATE KEY-----'))

    def test_jwt_is_signed_for_the_app(self):
        pem = subprocess.check_output(
            ['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048'],
            text=True, stderr=subprocess.DEVNULL)
        token = github_app.app_jwt(pem, now=1_700_000_000)
        header, payload, sig = token.split('.')
        self.assertEqual(_decode(header)['alg'], 'RS256')
        self.assertEqual(_decode(payload)['iss'], github_app.APP_ID)
        self.assertEqual(_decode(payload)['exp'] - _decode(payload)['iat'], 600)
        raw_sig = base64.urlsafe_b64decode(sig + '=' * (-len(sig) % 4))
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp, 'key.pem')
            pub = Path(tmp, 'pub.pem')
            signature = Path(tmp, 'sig')
            key.write_text(pem)
            signature.write_bytes(raw_sig)
            subprocess.run(['openssl', 'pkey', '-in', key, '-pubout', '-out', pub], check=True, capture_output=True)
            verified = subprocess.run(
                ['openssl', 'dgst', '-sha256', '-verify', pub, '-signature', signature],
                input=f'{header}.{payload}'.encode(), capture_output=True)
        self.assertEqual(verified.returncode, 0)


if __name__ == '__main__':
    unittest.main()
