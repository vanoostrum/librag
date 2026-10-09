"""Subprocess helper shared by the factory CLIs."""

import os
import subprocess

from github_app import git_auth_env, installation_token


def run(*args):
    env = os.environ.copy()
    app_token = None
    if args and args[0] == 'gh':
        app_token = installation_token()
        if app_token:
            # Replaces both the cloud git placeholder and any personal GH_TOKEN.
            env['GH_TOKEN'] = app_token
            env['GITHUB_TOKEN'] = app_token
    elif args and args[0] == 'git' and 'push' in args:
        env = git_auth_env(env)
        app_token = env.get('LIBRAG_GIT_TOKEN')
    try:
        return _run(args, env)
    except subprocess.CalledProcessError as error:
        # In Cursor cloud VMs GH_TOKEN holds a git-only placeholder that the API
        # rejects; the stored `cursor` gh login works once GH_TOKEN is unset.
        # An app token is never swapped out for that login.
        if app_token or args[0] != 'gh' or 'GH_TOKEN' not in os.environ or 'Bad credentials' not in (error.stderr or ''):
            raise
        return _run(args, {k: v for k, v in os.environ.items() if k != 'GH_TOKEN'})


def _run(args, env):
    return subprocess.run(args, check=True, capture_output=True, text=True, env=env).stdout.strip()
