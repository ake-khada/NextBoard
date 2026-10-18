"""Run one command with an owned emulator and ADB server, then stop both.

This must run in the offline device namespace. No host device discovery, service
attachment, data clearing, physical USB passthrough, or persistent daemon exists.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def main():
    if os.environ.get('NEXTBOARD_SANDBOX') != 'device':
        sys.exit('Device lifecycle requires the device sandbox')
    cfg = json.loads(Path('.local/dev.json').read_text())
    port = str(cfg['adb_port'])
    assert port != '5037' and os.environ['ANDROID_ADB_SERVER_PORT'] == port
    serial = f"emulator-{cfg['emulator_port']}"
    for value in (cfg['adb_port'], cfg['emulator_port'], cfg['emulator_port'] + 1):
        with socket.socket() as check:
            check.bind(('127.0.0.1', value))  # Fail on unknown services, even inside this namespace.
    avd = Path(os.environ['ANDROID_AVD_HOME']) / (cfg['avd'] + '.ini')
    if not avd.exists():
        image = next(p for p in cfg['sdk_packages'] if p.startswith('system-images;'))
        subprocess.run(['avdmanager', 'create', 'avd', '-n', cfg['avd'], '-k', image,
                        '--device', 'pixel_6'], input=b'no\n', check=True)
    output = Path('.local/device')
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'adb.log').open('w') as adb_log, (output / 'emulator.log').open('w') as emulator_log:
        adb = subprocess.Popen(['adb', '-L', f'tcp:localhost:{port}',
                                'server', 'nodaemon'], stdout=adb_log, stderr=subprocess.STDOUT)
        emulator = None
        try:
            time.sleep(0.5)
            if adb.poll() is not None:
                raise RuntimeError('Owned ADB server did not start')
            emulator = subprocess.Popen([
                'emulator', '-avd', cfg['avd'], '-port', str(cfg['emulator_port']),
                '-no-window', '-no-audio', '-no-snapshot', '-no-boot-anim',
                '-gpu', 'swiftshader', '-accel', 'on', '-cores', '2', '-memory', '2048',
                '-no-metrics', '-no-location-ui',
            ], stdout=emulator_log, stderr=subprocess.STDOUT)
            client = ['adb', '-P', port, '-s', serial]
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if emulator.poll() is not None:
                    raise RuntimeError('Emulator exited before boot; inspect the private emulator log')
                status = subprocess.run([*client, 'shell', 'getprop', 'sys.boot_completed'],
                                        capture_output=True, timeout=10)
                if status.stdout.strip() == b'1':
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Emulator boot timed out')
            name = subprocess.check_output([*client, 'emu', 'avd', 'name'], text=True).splitlines()[0]
            if name != cfg['avd']:
                raise RuntimeError('Unexpected emulator identity')
            # The command inherits an exact serial; scripts must still use -s explicitly.
            env = dict(os.environ, ANDROID_SERIAL=serial)
            print('Owned emulator booted in offline namespace', flush=True)
            return subprocess.run(sys.argv[1:], env=env).returncode
        finally:
            for process in (emulator, adb):
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == '__main__':
    sys.exit(main())
