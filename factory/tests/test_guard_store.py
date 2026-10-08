"""Race and replay behavior of the guard store. Git tests use a local bare repo."""

from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from guard_store import (
    GitRefStore, MemoryStore, begin, claim, ensure_ref, receipt_status, record_receipt, release,
)


class GuardStoreTests(unittest.TestCase):
    def test_parallel_claims_have_one_winner(self):
        store = MemoryStore()
        winners = []
        barrier = threading.Barrier(2)

        def attempt(owner):
            barrier.wait()
            if claim(store, 'LIBRAG-1', 'spec', owner, f'evt-{owner}', now=1000) == 'acquired':
                winners.append(owner)

        threads = [threading.Thread(target=attempt, args=(name,)) for name in ('a', 'b')]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(winners), 1)
        self.assertEqual(claim(store, 'LIBRAG-1', 'spec', 'c', 'evt-c', now=1001), 'busy')

    def test_stale_claim_can_be_recovered_by_a_new_owner(self):
        store = MemoryStore()
        self.assertEqual(claim(store, 'LIBRAG-1', 'build', 'a', 'evt-a', now=1000, ttl=10), 'acquired')
        self.assertEqual(claim(store, 'LIBRAG-1', 'build', 'b', 'evt-b', now=1011), 'acquired')

    def test_terminal_receipt_blocks_and_failed_can_retry(self):
        store = MemoryStore()
        self.assertEqual(record_receipt(store, 'delivery-1', {'outcome': 'success'}), 'ok')
        self.assertEqual(record_receipt(store, 'delivery-1', {'outcome': 'started'}), 'duplicate')
        self.assertEqual(receipt_status(store, 'delivery-1'), 'done')
        self.assertEqual(record_receipt(store, 'delivery-2', {'outcome': 'started'}), 'ok')
        self.assertEqual(record_receipt(store, 'delivery-2', {'outcome': 'failed'}), 'ok')
        self.assertEqual(receipt_status(store, 'delivery-2'), 'open')
        self.assertEqual(release(store, 'missing', 'a'), 'not-owner')
        with self.assertRaises(ValueError):
            record_receipt(store, 'delivery-3', {'outcome': 'maybe'})

    def test_begin_leaves_a_busy_event_unrecorded_and_retries_failure(self):
        store = MemoryStore()
        self.assertEqual(begin(store, 'LIBRAG-1', 'build', 'a', 'evt', now=1000), 'ok')
        self.assertEqual(begin(store, 'LIBRAG-1', 'build', 'b', 'evt-2', now=1001), 'busy')
        self.assertEqual(receipt_status(store, 'evt-2'), 'no')
        self.assertEqual(record_receipt(store, 'evt', {'outcome': 'failed'}), 'ok')
        self.assertEqual(release(store, 'LIBRAG-1', 'a'), 'ok')
        self.assertEqual(begin(store, 'LIBRAG-1', 'build', 'b', 'evt', now=1002), 'ok')
        self.assertEqual(record_receipt(store, 'evt', {'outcome': 'success'}), 'ok')
        self.assertEqual(release(store, 'LIBRAG-1', 'b'), 'ok')
        self.assertEqual(begin(store, 'LIBRAG-1', 'build', 'c', 'evt', now=1003), 'duplicate')
        self.assertEqual(claim(store, 'LIBRAG-1', 'build', 'd', 'evt-d', now=1004), 'acquired')


class GitRefStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.remote = root / 'remote.git'
        self.repo = root / 'repo'
        subprocess.run(['git', 'init', '--bare', '-b', 'main', self.remote], check=True, capture_output=True)
        subprocess.run(['git', 'init', '-b', 'main', self.repo], check=True, capture_output=True)
        subprocess.run(['git', '-C', self.repo, 'remote', 'add', 'origin', self.remote], check=True, capture_output=True)

    def test_stale_push_is_a_conflict_and_a_missing_remote_is_not(self):
        self.assertEqual(ensure_ref(self.repo, str(self.remote)), 'created')
        store = GitRefStore(self.repo, str(self.remote))
        sha, state = store.read()
        self.assertTrue(store.cas(sha, {'claims': {}, 'receipts': {'probe': {'outcome': 'success'}}}))
        self.assertFalse(store.cas(sha, state))
        store.remote = str(Path(self.tmp.name) / 'missing.git')
        with self.assertRaises(RuntimeError) as caught:
            store.cas(sha, state)
        self.assertNotIn('kept moving', str(caught.exception))

    def test_release_by_a_stranger_exits_nonzero(self):
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'guard_store.py'
        base = [sys.executable, str(script), '--repo', str(self.repo)]
        subprocess.run([*base, 'init'], check=True, capture_output=True, text=True)
        subprocess.run(
            [*base, 'claim', '--issue', 'LIBRAG-1', '--stage', 'build', '--owner', 'a', '--event', 'e1'],
            check=True, capture_output=True, text=True,
        )
        stranger = subprocess.run(
            [*base, 'release', '--issue', 'LIBRAG-1', '--owner', 'b'],
            capture_output=True, text=True,
        )
        self.assertEqual(stranger.returncode, 2)
        self.assertEqual(stranger.stdout.strip(), 'not-owner')
        owner = subprocess.run(
            [*base, 'release', '--issue', 'LIBRAG-1', '--owner', 'a'],
            capture_output=True, text=True,
        )
        self.assertEqual(owner.returncode, 0)
        self.assertEqual(owner.stdout.strip(), 'ok')


if __name__ == '__main__':
    unittest.main()
