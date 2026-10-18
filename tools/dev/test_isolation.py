"""Integration tests against real namespaces, using synthetic host fixtures only."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
import importlib.util

ROOT = Path(__file__).resolve().parents[2]


class IsolationTest(unittest.TestCase):
    def run_inside(self, code, *args):
        return subprocess.run([str(ROOT / 'dev'), '--', 'python3', '-c', code, *args],
                              cwd=ROOT, capture_output=True, text=True)

    def test_foreign_file_and_home_are_hidden(self):
        with tempfile.TemporaryDirectory(prefix='android-isolation-') as directory:
            foreign = Path(directory) / 'synthetic-secret'
            foreign.write_text('not user data')
            result = self.run_inside(
                'from pathlib import Path; import os,sys; '
                'assert not Path(sys.argv[1]).exists(); '
                'assert os.environ["HOME"] == sys.argv[2]; '
                'assert not Path("/run/user/1000/bus").exists()', str(foreign), os.environ['HOME'])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(foreign.read_text(), 'not user data')

    def test_host_listener_is_unreachable_and_unchanged(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            # Never contact a real ADB service; test an ephemeral synthetic listener.
            result = self.run_inside(
                'import socket,sys; s=socket.socket(); s.settimeout(.1); '
                'assert s.connect_ex(("127.0.0.1",int(sys.argv[1]))) != 0', str(port))
            self.assertEqual(result.returncode, 0, result.stderr)
            with socket.create_connection(('127.0.0.1', port)):
                connection, _ = listener.accept()
                connection.close()

    def test_private_tmp_and_environment(self):
        code = ('import os; from pathlib import Path; '
                'assert "SSH_AUTH_SOCK" not in os.environ; '
                'assert "DBUS_SESSION_BUS_ADDRESS" not in os.environ; '
                'assert not Path("/tmp/sandbox-marker").exists(); '
                'Path("/tmp/sandbox-marker").touch()')
        for _ in range(2):
            result = self.run_inside(code)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_effective_profile(self):
        result = subprocess.run([str(ROOT / 'dev'), 'check'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_adb_rejects_foreign_targets_without_launching_a_server(self):
        cfg = json.loads((ROOT / '.local/dev.json').read_text())
        env = dict(os.environ, NEXTBOARD_SANDBOX='device',
                   ANDROID_ADB_SERVER_PORT=str(cfg['adb_port']))
        for args in (['-P', '5037', 'devices'], ['-s', 'unexpected-device', 'get-state'],
                     ['-H', '192.0.2.1', 'devices'], ['kill-server'], ['connect', '192.0.2.1'],
                     ['devices']):
            result = subprocess.run([str(ROOT / '.toolchains/python/bin/python3'),
                                     str(ROOT / 'tools/dev/bin/adb'), *args],
                                    env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_rejects_foreign_state_before_creating_directories(self):
        spec = importlib.util.spec_from_file_location('sandbox_runner', ROOT / 'tools/dev/runner.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory(prefix='android-state-') as directory:
            base = Path(directory)
            project, foreign = base / 'project', base / 'foreign'
            project.mkdir(); foreign.mkdir()
            (project / '.toolchains').mkdir()
            (project / '.toolchains/android').symlink_to(foreign)
            runner.ROOT, runner.STATE = project, project / '.toolchains'
            with self.assertRaises(ValueError):
                runner.prepare()
            self.assertEqual(list(foreign.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
