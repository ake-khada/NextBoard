"""Startup checks must fail before launching owned device processes."""
from contextlib import chdir
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('device', Path(__file__).with_name('device.py'))
device = importlib.util.module_from_spec(spec)
spec.loader.exec_module(device)


class LaunchAttempt(Exception):
    """Stop startup at the process boundary without launching ADB or an emulator."""


class PreflightTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(chdir(directory))
        Path('.local').mkdir()
        avds = Path(directory) / 'avds'
        avds.mkdir()
        (avds / 'Test_AVD.ini').touch()
        self.enterContext(mock.patch.dict(os.environ, {
            'NEXTBOARD_SANDBOX': 'device',
            'ANDROID_ADB_SERVER_PORT': '5038',
            'ANDROID_AVD_HOME': str(avds),
        }))
        self.enterContext(mock.patch.object(device.socket, 'socket'))
        # Preflight commands execute normally; only lifecycle launches are intercepted.
        self.processes = self.enterContext(mock.patch.object(device, 'subprocess', wraps=subprocess))
        self.processes.Popen.side_effect = LaunchAttempt

    def write_config(self, **options):
        cfg = {'adb_port': 5038, 'emulator_port': 5554, 'avd': 'Test_AVD', **options}
        Path('.local/dev.json').write_text(json.dumps(cfg))

    def test_absent_preflight_allows_startup(self):
        self.write_config()
        with self.assertRaises(LaunchAttempt):
            device.main()
        self.processes.run.assert_not_called()
        self.processes.Popen.assert_called_once()
        self.assertEqual(self.processes.Popen.call_args.args[0][0], 'adb')

    def test_malformed_preflight_prevents_process_launch(self):
        for value in (False, None, '', {}, [], True, 0, 1, 'command',
                      {'command': 'check'}, [None], [''], ['', 'argument'],
                      ['command', None], ['command', False], ['command', 1],
                      ['command', []], ['command', {}]):
            with self.subTest(value=value):
                self.processes.reset_mock()
                self.write_config(device_preflight=value)
                with self.assertRaisesRegex(ValueError, 'device_preflight'):
                    device.main()
                self.processes.run.assert_not_called()
                self.processes.Popen.assert_not_called()

    def test_successful_preflight_allows_empty_non_executable_argument(self):
        command = [sys.executable, '-I', '-c', 'import sys; assert sys.argv[1:] == [""]', '']
        self.write_config(device_preflight=command)
        with self.assertRaises(LaunchAttempt):
            device.main()
        self.processes.run.assert_called_once_with(command, check=True, timeout=180)
        self.processes.Popen.assert_called_once()
        self.assertEqual(self.processes.Popen.call_args.args[0][0], 'adb')

    def test_failing_preflight_prevents_process_launch(self):
        command = [sys.executable, '-I', '-c', 'raise SystemExit(7)']
        self.write_config(device_preflight=command)
        with self.assertRaises(subprocess.CalledProcessError) as raised:
            device.main()
        self.assertEqual(raised.exception.returncode, 7)
        self.processes.run.assert_called_once_with(command, check=True, timeout=180)
        self.processes.Popen.assert_not_called()


class IdentityTest(unittest.TestCase):
    def test_verified_console_response(self):
        device.verify_identity(subprocess.CompletedProcess([], 0, 'Test_AVD\nOK\n', ''), 'Test_AVD')

    def test_failures_include_command_evidence(self):
        for result in (subprocess.CompletedProcess([], 0, '', 'console disconnected'),
                       subprocess.CompletedProcess([], 1, 'Test_AVD\n', 'failed'),
                       subprocess.CompletedProcess([], 0, 'Other_AVD\nOK\n', ''),
                       subprocess.CompletedProcess([], 0, 'Test_AVD\nOther_AVD\nOK\n', '')):
            with self.subTest(result=result), self.assertRaises(RuntimeError) as raised:
                device.verify_identity(result, 'Test_AVD')
            self.assertIn(f'exit={result.returncode}', str(raised.exception))
            self.assertIn(f'stdout={result.stdout!r}', str(raised.exception))
            self.assertIn(f'stderr={result.stderr!r}', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
