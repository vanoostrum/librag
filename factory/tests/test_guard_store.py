"""Race and replay behavior of the guard store. No network."""

from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from guard_store import MemoryStore, claim, receipt_exists, record_receipt, release


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

    def test_duplicate_receipt_does_not_record_twice(self):
        store = MemoryStore()
        self.assertEqual(record_receipt(store, 'delivery-1', {'stage': 'spec'}), 'ok')
        self.assertEqual(record_receipt(store, 'delivery-1', {'stage': 'spec'}), 'duplicate')
        self.assertTrue(receipt_exists(store, 'delivery-1'))
        self.assertEqual(release(store, 'missing', 'a'), 'not-owner')


if __name__ == '__main__':
    unittest.main()
