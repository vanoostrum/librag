"""Squash-merge an approved factory PR, but only at the approved head with every required check green.

The approver must be listed in factory/config.yaml, the approved spec revision
must still be the revision in the issue description, and the head SHA must
still be the PR head. Use --dry-run to check the gate without merging. Prints
`merged <sha>`, `ready`, or `refused: <reason>` (exit 2).
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

from cli import run
from policy import approval_matches, current_checks_green
import spec

CONFIG = Path(__file__).resolve().parents[1] / 'config.yaml'
STAGE = 'merge-gate'


class Refused(Exception):
    pass


def load_config(config_path=CONFIG):
    return yaml.safe_load(Path(config_path).read_text())


def required_checks(config_path=CONFIG):
    checks = load_config(config_path)['checks']
    return list(checks.get('factory_required') or []) + list(checks.get('project_required') or [])


def allowed_approvers(config_path=CONFIG):
    return list(load_config(config_path).get('approvals', {}).get('slack_user_ids') or [])


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


def merge_gate_record(issue, spec_rev, gate_ts, pr_number, head_sha):
    return {
        'issue_id': issue,
        'gate': 'merge',
        'spec_rev': str(spec_rev),
        'gate_message_ts': str(gate_ts),
        'pr_number': int(pr_number),
        'head_sha': head_sha,
    }


def check_approval(issue, spec_rev, gate_ts, approver, description, number, pr, allowed):
    current_rev, _ = spec.body(description)
    if not current_rev:
        raise Refused(f'{issue} has no spec')
    gate = merge_gate_record(issue, spec_rev, gate_ts, number, pr['headRefOid'])
    approval = dict(gate, user_id=approver)
    current = merge_gate_record(issue, current_rev, gate_ts, number, pr['headRefOid'])
    if not approval_matches(gate, approval, current, allowed):
        raise Refused('merge approval does not match this PR, spec revision, and approver')


def check_gate(number, issue, head, required, *, approver, spec_rev, gate_ts, description, allowed, run=run):
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
    check_approval(issue, spec_rev, gate_ts, approver, description, number, pr, allowed)
    return pr


def merge(number, issue, head, required, *, approver, spec_rev, gate_ts, description, allowed, run=run):
    pr = check_gate(
        number, issue, head, required,
        approver=approver, spec_rev=spec_rev, gate_ts=gate_ts,
        description=description, allowed=allowed, run=run,
    )
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
    parser.add_argument('--approver', required=True, help='Slack user id of the person who approved')
    parser.add_argument('--spec-rev', required=True, help='spec revision named by that approval')
    parser.add_argument('--gate-ts', required=True, help='timestamp of the merge-gate Slack message')
    parser.add_argument('--description', required=True, help='file with the current Linear issue description')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    required = required_checks()
    allowed = allowed_approvers()
    description = Path(args.description).read_text()
    try:
        if args.dry_run:
            check_gate(
                args.pr, args.issue, args.head, required,
                approver=args.approver, spec_rev=args.spec_rev, gate_ts=args.gate_ts,
                description=description, allowed=allowed,
            )
            print('ready')
        else:
            merged = merge(
                args.pr, args.issue, args.head, required,
                approver=args.approver, spec_rev=args.spec_rev, gate_ts=args.gate_ts,
                description=description, allowed=allowed,
            )
            print(f'merged {merged}')
    except Refused as reason:
        print(f'refused: {reason}')
        return 2
    except subprocess.CalledProcessError as error:
        print(error.stderr.strip() or error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
