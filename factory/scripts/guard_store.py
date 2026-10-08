"""Atomic claims and receipts on a shared git ref.

policy.py decides what a stage may do. This module only stores the facts that
decision needs: one live claim per issue and one receipt per event. begin claims
before it records, and only a finished receipt (success, noop, escalated) blocks
a retry. The compare and swap is a fast-forward push of refs/heads/factory-guards.
A rejected fast-forward means another writer committed first; the caller re-reads
and retries. Any other push failure is raised. Agent memory and Linear comments
are not locks.
"""

import argparse
import json
import subprocess
import sys
import threading
import time

REF = 'refs/heads/factory-guards'
STATE_PATH = 'state.json'
CLAIM_TTL_SECONDS = 900
# started/failed stay open so a crash or a busy rejection can be retried.
# success/noop/escalated are finished; a missing outcome is treated as finished.
RETRYABLE_OUTCOMES = frozenset({'started', 'failed'})
TERMINAL_OUTCOMES = frozenset({'success', 'noop', 'escalated'})
KNOWN_OUTCOMES = RETRYABLE_OUTCOMES | TERMINAL_OUTCOMES
PUSH_CONFLICT_MARKERS = ('non-fast-forward', 'fetch first', 'updates were rejected')


class StoreConflict(RuntimeError):
    pass


class MemoryStore:
    """In-process compare-and-swap used by tests and as the race model."""

    def __init__(self):
        self._lock = threading.Lock()
        self.sha = '0'
        self.state = {'claims': {}, 'receipts': {}}

    def read(self):
        with self._lock:
            return self.sha, json.loads(json.dumps(self.state))

    def cas(self, expected_sha, new_state):
        with self._lock:
            if expected_sha != self.sha:
                return False
            self.sha = str(int(self.sha) + 1)
            self.state = json.loads(json.dumps(new_state))
            return True


class GitRefStore:
    """Compare-and-swap through git commit-tree and a non-forced push."""

    def __init__(self, repo, remote='origin'):
        self.repo = repo
        self.remote = remote

    def read(self):
        self._git(['fetch', self.remote, REF])
        sha = self._git(['rev-parse', 'FETCH_HEAD']).strip()
        raw = self._git(['show', f'{sha}:{STATE_PATH}'])
        return sha, json.loads(raw)

    def cas(self, expected_sha, new_state):
        blob = self._git(
            ['hash-object', '-w', '--stdin'],
            input_text=json.dumps(new_state, sort_keys=True) + '\n',
        ).strip()
        tree = self._git(
            ['mktree'],
            input_text=f'100644 blob {blob}\t{STATE_PATH}\n',
        ).strip()
        commit = self._git([
            '-c', 'user.name=LibRag Factory',
            '-c', 'user.email=3648455+vanoostrum@users.noreply.github.com',
            'commit-tree', tree, '-p', expected_sha, '-m', 'factory guard',
        ]).strip()
        result = self._git(
            ['push', self.remote, f'{commit}:{REF}'],
            check=False,
        )
        if result.returncode == 0:
            return True
        if _push_conflict(result):
            return False
        detail = (result.stderr or result.stdout or '').strip()
        raise RuntimeError(detail[-800:] or f'git push failed ({result.returncode})')

    def _git(self, args, input_text=None, check=True):
        result = subprocess.run(
            ['git', *args],
            cwd=self.repo,
            input=input_text,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout or '').strip()
            raise RuntimeError(detail[-800:])
        if check:
            return result.stdout
        return result


def ensure_ref(repo, remote='origin'):
    """Create the guard ref when it is absent. Existing state is left in place."""
    listed = subprocess.run(
        ['git', 'ls-remote', remote, REF],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if listed.returncode != 0:
        raise RuntimeError((listed.stderr or '').strip()[-800:])
    if listed.stdout.strip():
        return 'present'
    store = GitRefStore(repo, remote)
    blob = store._git(
        ['hash-object', '-w', '--stdin'],
        input_text='{"claims": {}, "receipts": {}}\n',
    ).strip()
    tree = store._git(
        ['mktree'],
        input_text=f'100644 blob {blob}\t{STATE_PATH}\n',
    ).strip()
    commit = store._git([
        '-c', 'user.name=LibRag Factory',
        '-c', 'user.email=3648455+vanoostrum@users.noreply.github.com',
        'commit-tree', tree, '-m', 'factory guard init',
    ]).strip()
    pushed = store._git(['push', remote, f'{commit}:{REF}'], check=False)
    if pushed.returncode != 0:
        # Another initializer won the create.
        listed = subprocess.run(
            ['git', 'ls-remote', remote, REF],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if not listed.stdout.strip():
            raise RuntimeError((pushed.stderr or '').strip()[-800:])
    return 'created'


def _mutate(store, change, attempts=8):
    for _ in range(attempts):
        sha, state = store.read()
        outcome = change(state)
        if outcome is not None:
            return outcome
        if store.cas(sha, state):
            return 'ok'
    raise StoreConflict('guard ref kept moving')


def claim(store, issue, stage, owner, event_id, now=None, ttl=CLAIM_TTL_SECONDS):
    """Return acquired or busy. A stale claim can be taken; a live one cannot."""
    now = time.time() if now is None else now

    def change(state):
        claims = state.setdefault('claims', {})
        current = claims.get(issue)
        if current and current.get('expires', 0) > now and not (
            current.get('owner') == owner and current.get('event_id') == event_id
        ):
            return 'busy'
        claims[issue] = {
            'stage': stage,
            'owner': owner,
            'event_id': event_id,
            'expires': now + ttl,
        }
        return None

    result = _mutate(store, change)
    return 'acquired' if result == 'ok' else result


def release(store, issue, owner):
    def change(state):
        current = state.setdefault('claims', {}).get(issue)
        if not current or current.get('owner') != owner:
            return 'not-owner'
        del state['claims'][issue]
        return None

    return _mutate(store, change)


def _push_conflict(result):
    """A rejected fast-forward is a lost race. Auth and network failures are not."""
    text = f'{result.stderr or ""}\n{result.stdout or ""}'.lower()
    return any(marker in text for marker in PUSH_CONFLICT_MARKERS)


def record_receipt(store, event_id, receipt):
    outcome = receipt.get('outcome')
    if outcome not in KNOWN_OUTCOMES:
        raise ValueError(f'unknown receipt outcome {outcome!r}')

    def change(state):
        receipts = state.setdefault('receipts', {})
        current = receipts.get(event_id)
        if current and current.get('outcome') not in RETRYABLE_OUTCOMES:
            return 'duplicate'
        receipts[event_id] = receipt
        return None

    return _mutate(store, change)


def receipt_status(store, event_id):
    """done when the event finished, open when it can be retried, no when unseen."""
    _, state = store.read()
    current = state.get('receipts', {}).get(event_id)
    if not current:
        return 'no'
    if current.get('outcome') in RETRYABLE_OUTCOMES:
        return 'open'
    return 'done'


def receipt_exists(store, event_id):
    return receipt_status(store, event_id) != 'no'


def begin(store, issue, stage, owner, event_id, now=None):
    """Claim first, then record started. busy writes nothing. A finished event is released."""
    claimed = claim(store, issue, stage, owner, event_id, now=now)
    if claimed != 'acquired':
        return claimed
    try:
        receipt = record_receipt(store, event_id, {
            'stage': stage,
            'outcome': 'started',
            'at': time.time() if now is None else now,
        })
    except Exception:
        release(store, issue, owner)
        raise
    if receipt == 'duplicate':
        release(store, issue, owner)
        return 'duplicate'
    return 'ok'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    begin_cmd = sub.add_parser('begin', help='claim the issue, then record this event as started')
    begin_cmd.add_argument('--issue', required=True)
    begin_cmd.add_argument('--stage', required=True)
    begin_cmd.add_argument('--owner', required=True)
    begin_cmd.add_argument('--event', required=True)
    claim_cmd = sub.add_parser('claim')
    claim_cmd.add_argument('--issue', required=True)
    claim_cmd.add_argument('--stage', required=True)
    claim_cmd.add_argument('--owner', required=True)
    claim_cmd.add_argument('--event', required=True)
    release_cmd = sub.add_parser('release')
    release_cmd.add_argument('--issue', required=True)
    release_cmd.add_argument('--owner', required=True)
    seen = sub.add_parser('seen')
    seen.add_argument('--event', required=True)
    record = sub.add_parser('record')
    record.add_argument('--event', required=True)
    record.add_argument('--stage', required=True)
    record.add_argument('--outcome', required=True)
    args = parser.parse_args()
    if args.command == 'init':
        print(ensure_ref(args.repo))
        return 0
    store = GitRefStore(args.repo)
    if args.command == 'begin':
        result = begin(store, args.issue, args.stage, args.owner, args.event)
        print(result)
        return 0 if result == 'ok' else 2
    if args.command == 'claim':
        result = claim(store, args.issue, args.stage, args.owner, args.event)
        print(result)
        return 0 if result == 'acquired' else 2
    if args.command == 'release':
        result = release(store, args.issue, args.owner)
        print(result)
        return 0 if result == 'ok' else 2
    if args.command == 'seen':
        print(receipt_status(store, args.event))
        return 0
    try:
        receipt = record_receipt(store, args.event, {
            'stage': args.stage,
            'outcome': args.outcome,
            'at': time.time(),
        })
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    print(receipt)
    return 0 if receipt == 'ok' else 2


if __name__ == '__main__':
    raise SystemExit(main())
