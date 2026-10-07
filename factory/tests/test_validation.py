"""Ensure prepared placeholders cannot be mistaken for an active, correctly bound factory."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_factory import validate


class AssetValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        source = Path(__file__).resolve().parents[2]
        # Isolate mutations; never edit the checkout's actual readiness/bindings.
        shutil.copytree(source, self.root, ignore=shutil.ignore_patterns('.git', '__pycache__'))

    def change_config(self, mutate):
        path = self.root / 'factory/config.yaml'
        config = yaml.safe_load(path.read_text())
        mutate(config)
        path.write_text(yaml.safe_dump(config))

    def test_current_assets_pass_but_runtime_needs_real_prerequisites(self):
        self.assertEqual(validate(self.root), [])
        errors = validate(self.root, runtime=True)
        self.assertTrue(any('no named approvers' in error for error in errors))
        self.assertTrue(any('unverified slack_threads' in error for error in errors))
        self.assertTrue(any('unverified protected_merge' in error for error in errors))

    def test_activated_flag_cannot_bypass_runtime_validation(self):
        self.change_config(lambda config: config['runtime'].update(activated=True))
        self.assertTrue(any('Runtime:' in error for error in validate(self.root)))

    def test_publishing_and_premature_app_activation_are_rejected(self):
        self.change_config(lambda config: config['readiness'].update(
            publishing_enabled=True, application_implementation_enabled=True))
        errors = validate(self.root)
        self.assertTrue(any('Publishing must stay disabled' in error for error in errors))
        self.assertTrue(any('before step 3' in error for error in errors))

    def test_cross_project_destination_and_missing_skill_are_rejected(self):
        self.change_config(lambda config: config.update(repository='someone/another-project'))
        (self.root / '.agents/skills/factory/front-desk/SKILL.md').unlink()
        errors = validate(self.root)
        self.assertTrue(any('Wrong destination' in error for error in errors))
        self.assertTrue(any('missing skill' in error for error in errors))


if __name__ == '__main__':
    unittest.main()
