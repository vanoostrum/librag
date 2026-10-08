"""Subprocess helper shared by the factory CLIs."""

import os
import subprocess


def run(*args):
    try:
        return _run(args, os.environ)
    except subprocess.CalledProcessError as error:
        # In Cursor cloud VMs GH_TOKEN holds a git-only placeholder that the API
        # rejects; the stored `cursor` gh login works once GH_TOKEN is unset.
        if args[0] != 'gh' or 'GH_TOKEN' not in os.environ or 'Bad credentials' not in (error.stderr or ''):
            raise
        return _run(args, {k: v for k, v in os.environ.items() if k != 'GH_TOKEN'})


def _run(args, env):
    return subprocess.run(args, check=True, capture_output=True, text=True, env=env).stdout.strip()
