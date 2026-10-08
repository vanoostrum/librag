"""Branch, commit, and pull request conventions for factory issues.

branch  checks out the issue branch, reusing an existing `<key>-<num>/*` branch on retries.
commit  commits staged changes with the Factory-Issue and Factory-Stage trailers.
upsert  pushes the branch and creates or updates its PR with the standard title and body.
"""

import argparse
import json
import re
import subprocess
import sys

from cli import run

ISSUE = re.compile(r'^[A-Z][A-Z0-9]*-\d+$')


def issue_key(value):
    if not ISSUE.match(value):
        raise argparse.ArgumentTypeError(f'expected an issue key like LIBRAG-12, got {value!r}')
    return value


def slug(title, limit=40):
    words = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
    return words[:limit].rstrip('-') or 'change'


def prefix(issue):
    return issue.lower() + '/'


def branch_name(issue, title):
    return prefix(issue) + slug(title)


def existing_branch(issue, run=run):
    out = run('git', 'ls-remote', '--heads', 'origin')
    heads = sorted(name for line in out.splitlines() if 'refs/heads/' in line
                   for name in [line.split('refs/heads/', 1)[1]] if name.startswith(prefix(issue)))
    return heads[0] if heads else None


def checkout(issue, title, run=run):
    run('git', 'fetch', '--quiet', 'origin')
    found = existing_branch(issue, run)
    if found:
        run('git', 'switch', '--quiet', '-C', found, f'origin/{found}')
        return found
    name = branch_name(issue, title)
    run('git', 'switch', '--quiet', '-C', name, 'origin/main')
    return name


def commit(issue, stage, message, run=run):
    run('git', 'commit', '--quiet', '-m', message,
        '--trailer', f'Factory-Issue: {issue}', '--trailer', f'Factory-Stage: {stage}')
    return run('git', 'rev-parse', 'HEAD')


def cell(text):
    return ' '.join(str(text).split()).replace('|', '\\|')


def render_body(issue, rev, issue_url, thread, evidence, summary=''):
    rows = '\n'.join(f'| {cell(row["ac"])} | {cell(row["evidence"])} |' for row in evidence)
    parts = ['## Summary', '',
             f'Factory-Issue: {issue}',
             f'Spec: {issue_url}, rev {rev}',
             f'Slack-Thread: {thread}', '']
    if summary.strip():
        parts += [summary.strip(), '']
    parts += ['## Acceptance criteria and evidence', '',
              '| AC | Evidence |', '|---|---|', rows, '',
              'No publishing or deployment is part of this PR.', '']
    return '\n'.join(parts)


def load_evidence(path):
    with open(path) as handle:
        rows = json.load(handle)
    if not rows or not all(isinstance(r, dict) and r.get('ac') and r.get('evidence') for r in rows):
        raise ValueError('evidence must be a non-empty list of {"ac": ..., "evidence": ...}')
    return rows


def upsert(issue, title, body, run=run):
    branch = run('git', 'rev-parse', '--abbrev-ref', 'HEAD')
    if not branch.startswith(prefix(issue)):
        raise ValueError(f'current branch {branch} is not a {prefix(issue)}* branch')
    run('git', 'push', '--quiet', '-u', 'origin', 'HEAD')
    full_title = f'[{issue}] {title}'
    found = json.loads(run('gh', 'pr', 'list', '--head', branch, '--state', 'open',
                           '--json', 'number,url') or '[]')
    if found:
        run('gh', 'pr', 'edit', str(found[0]['number']), '--title', full_title, '--body', body)
        url, action = found[0]['url'], 'updated'
    else:
        url = run('gh', 'pr', 'create', '--base', 'main', '--head', branch,
                  '--title', full_title, '--body', body).splitlines()[-1]
        action = 'created'
    return action, url, run('git', 'rev-parse', 'HEAD')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    br = sub.add_parser('branch')
    br.add_argument('--issue', required=True, type=issue_key)
    br.add_argument('--title', required=True)
    cm = sub.add_parser('commit')
    cm.add_argument('--issue', required=True, type=issue_key)
    cm.add_argument('--stage', required=True)
    cm.add_argument('-m', '--message', required=True)
    up = sub.add_parser('upsert')
    up.add_argument('--issue', required=True, type=issue_key)
    up.add_argument('--title', required=True)
    up.add_argument('--rev', required=True, type=int)
    up.add_argument('--issue-url', required=True)
    up.add_argument('--thread', required=True, help='Slack thread permalink')
    up.add_argument('--evidence', required=True, help='JSON file: [{"ac": "1. ...", "evidence": "..."}]')
    up.add_argument('--summary', default='')
    args = parser.parse_args()
    try:
        if args.command == 'branch':
            print(checkout(args.issue, args.title))
        elif args.command == 'commit':
            print(commit(args.issue, args.stage, args.message))
        else:
            body = render_body(args.issue, args.rev, args.issue_url, args.thread,
                               load_evidence(args.evidence), args.summary)
            action, url, head = upsert(args.issue, args.title, body)
            print(f'{action} {url} {head}')
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as error:
        print(error.stderr.strip() or error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
