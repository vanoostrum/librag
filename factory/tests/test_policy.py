"""Exercise semantic guard boundaries; this does not simulate live integrations."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from policy import approval_matches, current_checks_green, eligible_work, event_decision


class GuardPolicyTests(unittest.TestCase):
    def test_factory_before_app_and_no_scope_escape(self):
        self.assertTrue(eligible_work(1, 'factory-docs', ['docs/factory-handoff.md']))
        for path in ['src/librag/main.py', 'Dockerfile', '../docs/x.md', 'docs/../src/app.py']:
            with self.subTest(path=path):
                self.assertFalse(eligible_work(1, 'factory-docs', [path]))
        for step in (1, 2):
            self.assertFalse(eligible_work(step, 'application', project_adapter=True))
        self.assertFalse(eligible_work(3, 'application', project_adapter=False))
        self.assertTrue(eligible_work(3, 'application', project_adapter=True))

    def test_all_checks_at_exact_revision(self):
        checks = {'Factory Contracts': {'sha': 'new', 'conclusion': 'success'},
                  'Project': {'sha': 'old', 'conclusion': 'success'}}
        self.assertTrue(current_checks_green(['Factory Contracts'], checks, 'new'))
        self.assertFalse(current_checks_green(['Factory Contracts', 'Project'], checks, 'new'))
        self.assertFalse(current_checks_green(['Missing'], checks, 'new'))
        for outcome in ('pending', 'skipped', 'neutral', 'failure'):
            checks['Project'] = {'sha': 'new', 'conclusion': outcome}
            self.assertFalse(current_checks_green(['Factory Contracts', 'Project'], checks, 'new'))

    def test_merge_approval_binds_revision_message_head_and_person(self):
        gate = dict(issue_id='i', gate='merge', pr_number=7, head_sha='head', spec_rev='2', gate_message_ts='ts')
        approval = dict(gate, user_id='human')
        self.assertTrue(approval_matches(gate, approval, gate, ['human']))
        self.assertFalse(approval_matches(gate, approval, gate, ['other']))
        for field in ('head_sha', 'spec_rev', 'gate_message_ts', 'pr_number'):
            current = dict(gate, **{field: 'changed'})
            self.assertFalse(approval_matches(gate, approval, current, ['human']))
        self.assertFalse(approval_matches(dict(gate, invalidated=True), approval, gate, ['human']))

    def test_spec_approval_needs_no_pr_but_binds_revision(self):
        gate = dict(issue_id='i', gate='spec', spec_rev='3', gate_message_ts='ts')
        approval = dict(gate, user_id='human')
        self.assertTrue(approval_matches(gate, approval, gate, ['human']))
        self.assertFalse(approval_matches(gate, approval, dict(gate, spec_rev='4'), ['human']))
        self.assertFalse(approval_matches(dict(gate, gate='unknown'), approval, gate, ['human']))

    def facts(self):
        return dict(binding_matches=True, already_processed=False, claim_owned=True, attempts=0,
                    factory_pr=True, open_pr=True, event_sha='new', head_sha='new',
                    state='Verifying', approved_spec=True, all_checks_green=True)

    def test_unrelated_and_stale_ci_never_enter_review(self):
        facts = self.facts()
        self.assertEqual(event_decision('review', facts), 'allow')
        facts['factory_pr'] = False
        self.assertEqual(event_decision('review', facts), 'noop')
        facts['factory_pr'] = True
        facts['event_sha'] = 'old'
        self.assertEqual(event_decision('review', facts), 'noop')
        facts['event_sha'] = 'new'
        facts['all_checks_green'] = False
        self.assertEqual(event_decision('review', facts), 'wait')

    def test_replay_ownership_and_no_fourth_attempt(self):
        facts = self.facts()
        for field, value, expected in [('already_processed', True, 'noop'),
                                       ('claim_owned', False, 'wait'), ('attempts', 3, 'escalate')]:
            changed = dict(facts, **{field: value})
            self.assertEqual(event_decision('ci-fix', changed), expected)

    def test_feedback_and_confirmed_merge(self):
        facts = self.facts()
        facts['feedback_owner'] = 'build'
        self.assertEqual(event_decision('comment-fix', facts), 'noop')
        facts['feedback_owner'] = 'comment-fix'
        self.assertEqual(event_decision('comment-fix', facts), 'allow')
        facts['merged'] = False
        self.assertEqual(event_decision('merge-completed', facts), 'wait')
        facts.update(merged=True, approved_merged_head=False, merge_sha='merge')
        self.assertEqual(event_decision('merge-completed', facts), 'escalate')
        facts['approved_merged_head'] = True
        self.assertEqual(event_decision('merge-completed', facts), 'allow')


if __name__ == '__main__':
    unittest.main()
