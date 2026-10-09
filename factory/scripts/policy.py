"""Pure guard decisions on freshly queried facts; no API, receipts or locks are implemented here."""

from pathlib import PurePosixPath


def eligible_work(step, work_kind, changed_paths=(), project_adapter=False):
    if work_kind == 'application':
        return step == 3 and project_adapter
    if work_kind != 'factory-docs':
        return False
    # An empty list is a missing diff, not an in-scope change.
    if not changed_paths:
        return False
    files = {'AGENTS.md', 'README.md', 'SETUP_LOG.md', '.gitignore',
             '.github/pull_request_template.md', '.github/workflows/factory-contracts.yml'}
    prefixes = ('docs/', 'factory/', '.agents/skills/factory/')
    for path in changed_paths:
        parts = PurePosixPath(path).parts
        if not path or path.startswith('/') or '..' in parts or '\\' in path:
            return False
        if path not in files and not path.startswith(prefixes):
            return False
    return True


def scope_violations(step, paths, application_enabled=False, project_adapter=False):
    """Paths a change may not touch at this readiness. An empty diff has none."""
    if application_enabled and project_adapter and step == 3:
        return []
    # Step 2 is the one-off project setup, which creates the application tree.
    if step == 2:
        return []
    return [path for path in paths if not eligible_work(step, 'factory-docs', [path])]


def current_checks_green(required, checks, head_sha):
    """Every required check must report success at this exact PR head."""
    if not required or not head_sha:
        return False
    return all(checks.get(name, {}).get('sha') == head_sha
               and checks.get(name, {}).get('conclusion') == 'success'
               for name in required)


GATE_FIELDS = {
    'spec': ('issue_id', 'gate', 'spec_rev', 'gate_message_ts'),
    'merge': ('issue_id', 'gate', 'spec_rev', 'gate_message_ts', 'pr_number', 'head_sha'),
}


def approval_matches(gate, approval, current, allowed_users):
    fields = GATE_FIELDS.get(gate.get('gate'))
    if not fields or not allowed_users or approval.get('user_id') not in allowed_users:
        return False
    if not all(gate.get(key) and approval.get(key) == gate[key]
               and current.get(key) == gate[key] for key in fields):
        return False
    return not gate.get('invalidated', False)


def event_decision(stage, facts):
    """Return allow/noop/wait/escalate. Caller must enforce durable ownership externally.

    Irrelevant events noop before the attempt cap, so a stale or foreign delivery
    cannot move an issue to Needs human.
    """
    if not facts.get('binding_matches'):
        return 'noop'
    if facts.get('already_processed'):
        return 'noop'
    if stage == 'front-desk' and facts.get('is_bot'):
        return 'noop'
    if stage in ('review', 'ci-fix', 'comment-fix', 'merge-completed') and not facts.get('factory_pr'):
        return 'noop'
    if stage in ('review', 'ci-fix', 'comment-fix'):
        if not facts.get('open_pr') or facts.get('event_sha') != facts.get('head_sha'):
            return 'noop'
    if stage == 'comment-fix' and facts.get('feedback_owner') != 'comment-fix':
        return 'noop'
    if stage == 'review' and facts.get('state') not in ('Verifying', 'Reviewing'):
        return 'noop'
    if not facts.get('claim_owned'):
        return 'wait'
    if stage == 'review':
        if not facts.get('approved_spec') or not facts.get('all_checks_green'):
            return 'wait'
    if stage == 'merge-completed':
        if not facts.get('merged'):
            return 'wait'
        if not facts.get('approved_merged_head') or not facts.get('merge_sha'):
            return 'escalate'
    if facts.get('attempts', 0) >= 3:
        return 'escalate'
    return 'allow'
