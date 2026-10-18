import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


spec = importlib.util.spec_from_file_location('guard', Path(__file__).parents[1] / 'check_public_tree.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class PolicyTest(unittest.TestCase):
    def test_local_paths_cannot_be_published(self):
        for path in (
            'AGENTS.md', 'PROGRESS.md', 'NEXTWORD_SPEC.md', 'BOOTSTRAP.md',
            '.local/plan.md', '.toolchains/sdk/file', '.privacy-local-patterns',
            'tools/.env', 'local.properties', 'signing.p12', 'example.local.md',
            'nextboard-session-example.md', 'out/example.apk',
        ):
            with self.subTest(path=path):
                self.assertTrue(guard.private_path(path))

    def test_public_source_and_generic_documentation_are_allowed(self):
        for path in ('app/Main.kt', 'tools/privacy/README.md', 'mise.toml', '.env.example'):
            self.assertFalse(guard.private_path(path))

    def test_shared_upstream_ide_files_still_have_content_checks(self):
        path = '.idea/codeStyles/Project.xml'
        self.assertFalse(guard.private_path(path))
        self.assertTrue(guard.findings(path, b'private-fixture', [b'private-fixture']))
        self.assertTrue(guard.private_path('.idea/workspace.xml'))
        self.assertTrue(guard.private_path('.idea/codeStyles/Private.xml'))

    def test_detector_does_not_echo_sensitive_values(self):
        examples = (
            b'/' + b'home/' + b'fixture/project/',
            b'/' + b'Users/' + b'fixture/project/',
            b'C:' + b'\\Users\\' + b'fixture\\project',
            b'adb -P 5999 -s ' + b'SYNTHETIC' * 2,
            b'firstInstallTime=' + b'2000-01-01',
            b'-----BEGIN ' + b'PRIVATE KEY-----',
            b'ghp_' + b'x' * 36,
        )
        for example in examples:
            with self.subTest(prefix=example[:4]):
                issues = guard.findings('file', example)
                self.assertTrue(issues)
                self.assertNotIn(example.decode(), str(issues))

    def test_parameterized_device_and_home_paths_are_allowed(self):
        self.assertEqual([], guard.findings('file', b'adb -s "$DEVICE" shell\n${HOME}/sdk\nadb -s emulator-5554 shell'))

    def test_local_patterns_are_case_insensitive_and_redacted(self):
        result = guard.findings('file', b'Private-Fixture', [b'private-fixture'])
        self.assertTrue(result)
        self.assertNotIn('Private-Fixture', str(result))


class RepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@users.noreply.github.com')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE)

    def write(self, path, content):
        file = self.repo / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)

    def test_clean_worktree_does_not_hide_staged_secret(self):
        self.write('source', b'ghp_' + b'a' * 36)
        self.git('add', 'source')
        self.write('source', b'clean')
        self.assertTrue(any('index:' in item for item in guard.check(self.repo, index_only=True)))

    def test_untracked_publishable_files_are_checked(self):
        self.write('.privacy-local-patterns', b'private-fixture\n')
        self.write('.gitignore', b'.privacy-local-patterns\n')
        self.git('add', '.gitignore')
        self.write('new file', b'private-fixture')
        self.assertEqual([], guard.check(self.repo, index_only=True))
        self.assertTrue(any('worktree: new file' in item for item in guard.check(self.repo)))

    def test_ignored_records_remain_private_even_if_force_added(self):
        self.write('.gitignore', b'.local/\n')
        self.git('add', '.gitignore')
        self.write('.local/plan.md', b'local-only')
        self.assertEqual([], guard.check(self.repo))
        self.git('add', '-f', '.local/plan.md')
        self.assertTrue(guard.check(self.repo, index_only=True))

    def test_untracking_preserves_local_document(self):
        self.write('PROGRESS.md', b'private notes')
        self.git('add', 'PROGRESS.md')
        self.git('commit', '-qm', 'Fixture')
        self.write('.gitignore', b'PROGRESS.md\n')
        self.git('add', '.gitignore')
        self.git('rm', '--cached', 'PROGRESS.md')
        self.assertEqual([], guard.check(self.repo))
        self.assertEqual(b'private notes', (self.repo / 'PROGRESS.md').read_bytes())

    def test_symlink_targets_are_checked_without_reading_them(self):
        self.write('.gitignore', b'.local/\n')
        self.write('.local/private', b'ghp_' + b'x' * 36)
        (self.repo / 'link').symlink_to('.local/private')
        self.git('add', '.gitignore', 'link')
        issues = guard.check(self.repo)
        self.assertTrue(any('symlink' in item for item in issues))
        self.assertFalse(any('access token' in item for item in issues))

    def test_safe_relative_source_link_is_allowed(self):
        self.write('source', b'public')
        (self.repo / 'link').symlink_to('source')
        self.git('add', 'source', 'link')
        self.assertEqual([], guard.check(self.repo))

    def test_commit_message_uses_private_denylist(self):
        self.write('.privacy-local-patterns', b'private-fixture\n')
        self.write('message', b'Fix for PRIVATE-FIXTURE')
        issues = guard.check(self.repo, message=self.repo / 'message')
        self.assertTrue(issues)
        self.assertNotIn('PRIVATE-FIXTURE', str(issues))

    def test_effective_identity_requires_noreply_and_checks_denylist(self):
        self.git('config', 'user.email', 'private@example.invalid')
        issues = guard.check(self.repo, index_only=True, identities=True)
        self.assertEqual(2, len(issues))
        self.assertNotIn('private@example.invalid', str(issues))
        self.git('config', 'user.email', 'fixture@users.noreply.github.com')
        self.assertEqual([], guard.check(self.repo, index_only=True, identities=True))
        self.write('.privacy-local-patterns', b'fixture@users.noreply.github.com\n')
        self.assertEqual(2, len(guard.check(self.repo, index_only=True, identities=True)))


if __name__ == '__main__':
    unittest.main()
