"""Squash-merge an approved factory PR, but only at the approved head with every required check green.

Run only after front desk has validated the human merge approval. Use --dry-run
to check the gate without merging. Prints `merged <sha>`, `ready`, or
`refused: <reason>` (exit 2).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

from cli import run
from policy import current_checks_green

CONFIG = Path(__file__).resolve().parents[1] / 'config.yaml'
STAGE = 'merge-gate'


class Refused(Exception):
    pass


def required_checks(config_path=CONFIG):
    checks = yaml.safe_load(Path(config_path).read_text())['checks']
    return list(checks.get('factory_required') or []) + list(checks.get('project_required') or [])


def pr_state(number, run=run):
    return json.loads(run('gh', 'pr', 'view', str(number), '--json',
                          'state,isDraft,baseRefName,headRefName,headRefOid,title,mergeCommit'))


def head_checks(sha, run=run):
    """Latest check run per name on this commit."""
    out = run('gh', 'api', '--paginate', f'repos/{{owner}}/{{repo}}/commits/{sha}/check-runs',
              '--jq', '.check_runs[] | [.id, .name, .head_sha, (.conclusion // "pending")] | @tsv')
    latest = {}
    for line in out.splitlines():
        run_id, name, head, conclusion = line.split('\t')
        if name not in latest or int(run_id) > latest[name][0]:
            latest[name] = (int(run_id), {'sha': head, 'conclusion': conclusion})
    return {name: value for name, (_, value) in latest.items()}


def check_gate(number, issue, head, required, run=run):
    pr = pr_state(number, run)
    if pr['state'] != 'OPEN' or pr['isDraft']:
        raise Refused(f'PR #{number} is {"draft" if pr["isDraft"] else pr["state"].lower()}')
    if pr['baseRefName'] != 'main':
        raise Refused(f'PR #{number} targets {pr["baseRefName"]}, not main')
    if not pr['headRefName'].startswith(issue.lower() + '/'):
        raise Refused(f'branch {pr["headRefName"]} does not belong to {issue}')
    if pr['headRefOid'] != head:
        raise Refused(f'head moved to {pr["headRefOid"]}; approval was for {head}')
    checks = head_checks(head, run)
    if not current_checks_green(required, checks, head):
        state = ', '.join(f'{name}={checks.get(name, {}).get("conclusion", "missing")}' for name in required)
        raise Refused(f'required checks not green on {head[:12]}: {state or "none configured"}')
    return pr


def merge(number, issue, head, required, run=run):
    pr = check_gate(number, issue, head, required, run)
    title = pr['title'] if pr['title'].startswith(f'[{issue}]') else f'[{issue}] {pr["title"]}'
    run('gh', 'pr', 'merge', str(number), '--squash', '--match-head-commit', head,
        '--subject', f'{title} (#{number})',
        '--body', f'Factory-Issue: {issue}\nFactory-Stage: {STAGE}')
    after = pr_state(number, run)
    if after['state'] != 'MERGED' or not after.get('mergeCommit'):
        raise Refused(f'merge command returned but PR #{number} is {after["state"].lower()}')
    return after['mergeCommit']['oid']


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pr', required=True, type=int)
    parser.add_argument('--issue', required=True, help='issue key, e.g. LIBRAG-12')
    parser.add_argument('--head', required=True, help='head SHA from the approved merge gate')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    required = required_checks()
    try:
        if args.dry_run:
            check_gate(args.pr, args.issue, args.head, required)
            print('ready')
        else:
            print(f'merged {merge(args.pr, args.issue, args.head, required)}')
    except Refused as reason:
        print(f'refused: {reason}')
        return 2
    except subprocess.CalledProcessError as error:
        print(error.stderr.strip() or error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
