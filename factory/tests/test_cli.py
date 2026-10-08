"""Exercise the factory CLIs with a fake command runner; no git or GitHub calls."""

from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import merge
import pr
import spec


class FakeRun:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        for prefix, output in self.responses:
            if args[:len(prefix)] == prefix:
                return output() if callable(output) else output
        return ''


class GhFallbackTests(unittest.TestCase):
    def test_rejected_gh_token_retries_with_stored_login(self):
        import cli
        import os
        import stat
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp, 'gh')
            fake.write_text('#!/bin/sh\n[ -n "$GH_TOKEN" ] && { echo "HTTP 401: Bad credentials" >&2; exit 1; }\necho stored\n')
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            env = dict(os.environ, PATH=f'{tmp}:{os.environ["PATH"]}', GH_TOKEN='placeholder')
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(cli.run('gh', 'pr', 'list'), 'stored')


class SpecTests(unittest.TestCase):
    def test_first_spec_is_appended_as_rev_1(self):
        new, rev, changed = spec.update('Request text.\n\nSlack-Thread: x\n', 'Goal: g\n')
        self.assertEqual((rev, changed), (1, True))
        self.assertEqual(new, 'Request text.\n\nSlack-Thread: x\n\n## Spec (rev 1)\nGoal: g\n<!-- /spec -->\n')

    def test_replace_keeps_other_sections_and_increments(self):
        description = 'Intro\n\n## Spec (rev 2)\nGoal: old\n\n## Notes\nkeep\n'
        new, rev, changed = spec.update(description, '## Spec (rev 9)\nGoal: new')
        self.assertEqual((rev, changed), (3, True))
        self.assertEqual(new, 'Intro\n\n## Spec (rev 3)\nGoal: new\n<!-- /spec -->\n\n## Notes\nkeep\n')
        self.assertEqual(spec.body(new), (3, 'Goal: new'))

    def test_headings_inside_the_spec_round_trip(self):
        text = '## Goal\nShip the guide\n\n## Acceptance criteria\n1. The guide exists'
        new, rev, changed = spec.update('Request.\n', text)
        self.assertEqual((rev, changed), (1, True))
        self.assertEqual(spec.body(new), (1, text))
        again, rev2, changed2 = spec.update(new + '\n## Notes\nkeep\n', '## Goal\nChanged')
        self.assertEqual((rev2, changed2), (2, True))
        self.assertEqual(spec.body(again), (2, '## Goal\nChanged'))
        self.assertIn('## Notes\nkeep\n', again)
        self.assertNotIn('Ship the guide', spec.body(again)[1])

    def test_identical_spec_keeps_revision(self):
        description = '## Spec (rev 4)\nGoal: same\n'
        self.assertEqual(spec.update(description, 'Goal: same\n'), (description, 4, False))

    def test_empty_spec_is_rejected(self):
        with self.assertRaises(ValueError):
            spec.update('x', '## Spec (rev 1)\n  \n')


class PrTests(unittest.TestCase):
    def test_branch_name_and_retry_reuse(self):
        self.assertEqual(pr.branch_name('LIBRAG-12', 'Add the Handoff guide!'), 'librag-12/add-the-handoff-guide')
        heads = 'a\trefs/heads/main\nb\trefs/heads/librag-12/old-slug\nc\trefs/heads/librag-120/other\n'
        run = FakeRun([(('git', 'ls-remote'), heads)])
        self.assertEqual(pr.checkout('LIBRAG-12', 'new title', run), 'librag-12/old-slug')
        self.assertIn(('git', 'switch', '--quiet', '-C', 'librag-12/old-slug', 'origin/librag-12/old-slug'), run.calls)
        run = FakeRun([(('git', 'ls-remote'), 'a\trefs/heads/librag-120/other\n')])
        self.assertEqual(pr.checkout('LIBRAG-12', 'New guide', run), 'librag-12/new-guide')

    def test_checkout_refuses_multiple_branches(self):
        heads = 'a\trefs/heads/librag-12/older\nb\trefs/heads/librag-12/newer\n'
        run = FakeRun([(('git', 'ls-remote'), heads)])
        with self.assertRaises(ValueError):
            pr.checkout('LIBRAG-12', 'title', run)
        self.assertFalse(any(c[1] == 'switch' for c in run.calls))

    def test_commit_adds_trailers(self):
        run = FakeRun([(('git', 'rev-parse'), 'abc')])
        self.assertEqual(pr.commit('LIBRAG-12', 'build', 'Add guide', run), 'abc')
        self.assertEqual(run.calls[0], ('git', 'commit', '--quiet', '-m', 'Add guide', '--trailer',
                                        'Factory-Issue: LIBRAG-12', '--trailer', 'Factory-Stage: build'))

    def test_body_lists_spec_thread_and_escaped_evidence(self):
        body = pr.render_body('LIBRAG-12', 3, 'https://linear.app/x', 'https://slack/t',
                              [{'ac': '1. a | b', 'evidence': 'docs/x.md\nline 4'}])
        self.assertIn('Spec: https://linear.app/x, rev 3', body)
        self.assertIn('Slack-Thread: https://slack/t', body)
        self.assertIn('| 1. a \\| b | docs/x.md line 4 |', body)

    def test_upsert_creates_then_updates(self):
        diff = (('git', 'diff', '--name-only'), 'docs/factory-handoff.md\n')
        run = FakeRun([(('git', 'rev-parse', '--abbrev-ref'), 'librag-12/guide'), diff,
                       (('gh', 'pr', 'list'), '[]'),
                       (('gh', 'pr', 'create'), 'https://github.com/o/r/pull/5'),
                       (('git', 'rev-parse', 'HEAD'), 'sha1')])
        self.assertEqual(pr.upsert('LIBRAG-12', 'Guide', 'body', run), ('created', 'https://github.com/o/r/pull/5', 'sha1'))
        self.assertIn('[LIBRAG-12] Guide', next(c for c in run.calls if c[:3] == ('gh', 'pr', 'create')))
        run = FakeRun([(('git', 'rev-parse', '--abbrev-ref'), 'librag-12/guide'), diff,
                       (('gh', 'pr', 'list'), json.dumps([{'number': 5, 'url': 'u'}])),
                       (('git', 'rev-parse', 'HEAD'), 'sha2')])
        self.assertEqual(pr.upsert('LIBRAG-12', 'Guide', 'body', run), ('updated', 'u', 'sha2'))

    def test_upsert_refuses_empty_or_out_of_scope_diffs(self):
        branch = (('git', 'rev-parse', '--abbrev-ref'), 'librag-12/guide')
        for diff, snippet in (
            ('', 'no changes'),
            ('src/librag/main.py\n', 'outside factory scope'),
        ):
            run = FakeRun([branch, (('git', 'diff', '--name-only'), diff)])
            with self.subTest(diff=diff or 'empty'), self.assertRaises(ValueError) as caught:
                pr.upsert('LIBRAG-12', 'Guide', 'body', run)
            self.assertIn(snippet, str(caught.exception))
            self.assertFalse(any(c[:2] == ('git', 'push') for c in run.calls))

    def test_upsert_refuses_foreign_branch(self):
        run = FakeRun([(('git', 'rev-parse', '--abbrev-ref'), 'main')])
        with self.assertRaises(ValueError):
            pr.upsert('LIBRAG-12', 'Guide', 'body', run)
        self.assertEqual(len(run.calls), 1)


class MergeTests(unittest.TestCase):
    DESC = '## Spec (rev 4)\nGoal\n'
    APPROVED = dict(approver='human', spec_rev='4', gate_ts='ts', description=DESC, allowed=['human'])

    def fake(self, head='h1', checks='1\tFactory Contracts\th1\tsuccess\n', merged=True, **pr_fields):
        state = dict(state='OPEN', isDraft=False, baseRefName='main', headRefName='librag-12/guide',
                     headRefOid=head, title='[LIBRAG-12] Guide', mergeCommit=None)
        state.update(pr_fields)
        views = [state, dict(state, state='MERGED' if merged else 'OPEN',
                             mergeCommit={'oid': 'm1'} if merged else None)]
        return FakeRun([(('gh', 'pr', 'view'), lambda: json.dumps(views.pop(0))),
                        (('gh', 'api'), checks)])

    def test_merges_approved_head_with_trailers(self):
        run = self.fake()
        self.assertEqual(merge.merge(5, 'LIBRAG-12', 'h1', ['Factory Contracts'], run=run, **self.APPROVED), 'm1')
        call = next(c for c in run.calls if c[:3] == ('gh', 'pr', 'merge'))
        self.assertEqual(call[call.index('--match-head-commit') + 1], 'h1')
        self.assertEqual(call[call.index('--subject') + 1], '[LIBRAG-12] Guide (#5)')
        self.assertEqual(call[call.index('--body') + 1], 'Factory-Issue: LIBRAG-12\nFactory-Stage: merge-gate')

    def test_refuses_moved_head_red_or_missing_checks(self):
        cases = {
            'moved head': self.fake(head='h2'),
            'failed check': self.fake(checks='1\tFactory Contracts\th1\tfailure\n'),
            'pending check': self.fake(checks='1\tFactory Contracts\th1\tpending\n'),
            'missing check': self.fake(checks=''),
            'rerun failed': self.fake(checks='1\tFactory Contracts\th1\tsuccess\n2\tFactory Contracts\th1\tfailure\n'),
            'foreign branch': self.fake(headRefName='librag-13/x'),
        }
        for name, run in cases.items():
            with self.subTest(name), self.assertRaises(merge.Refused):
                merge.merge(5, 'LIBRAG-12', 'h1', ['Factory Contracts'], run=run, **self.APPROVED)
            self.assertFalse(any(c[:3] == ('gh', 'pr', 'merge') for c in run.calls), name)

    def test_no_required_checks_refuses(self):
        with self.assertRaises(merge.Refused):
            merge.check_gate(5, 'LIBRAG-12', 'h1', [], run=self.fake(), **self.APPROVED)

    def test_unconfirmed_merge_is_reported(self):
        with self.assertRaises(merge.Refused):
            merge.merge(5, 'LIBRAG-12', 'h1', ['Factory Contracts'], run=self.fake(merged=False), **self.APPROVED)

    def test_refuses_when_approver_or_spec_rev_does_not_match(self):
        cases = {
            'stranger': dict(self.APPROVED, approver='stranger'),
            'empty allow list': dict(self.APPROVED, allowed=[]),
            'spec moved': dict(self.APPROVED, spec_rev='5'),
            'blank gate': dict(self.APPROVED, gate_ts=''),
        }
        for name, approval in cases.items():
            run = self.fake()
            with self.subTest(name), self.assertRaises(merge.Refused) as caught:
                merge.merge(5, 'LIBRAG-12', 'h1', ['Factory Contracts'], run=run, **approval)
            self.assertIn('approval', str(caught.exception))
            self.assertFalse(any(c[:3] == ('gh', 'pr', 'merge') for c in run.calls))

    def test_required_checks_and_approvers_come_from_config(self):
        self.assertEqual(merge.required_checks(), ['Factory Contracts'])
        self.assertEqual(merge.allowed_approvers(), ['U0C4NGQ0QFP'])


if __name__ == '__main__':
    unittest.main()
