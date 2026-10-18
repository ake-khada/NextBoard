"""Give a command access to one explicitly authorized phone and owned ADB server."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def main():
    if os.environ.get('NEXTBOARD_SANDBOX') != 'phone':
        raise RuntimeError('Phone access requires its sandbox profile')
    cfg = json.loads(Path('.local/dev.json').read_text())
    port, serial = str(cfg['adb_port']), cfg['phone']['serial']
    if port == '5037' or os.environ['ANDROID_ADB_SERVER_PORT'] != port:
        raise RuntimeError('Unexpected ADB environment')
    if sys.argv[1:2] == ['--diagnose']:
        return subprocess.run(sys.argv[2:]).returncode
    with socket.socket() as check:
        check.bind(('127.0.0.1', int(port)))
    with Path('.local/phone-adb.log').open('w') as log:
        server = subprocess.Popen(['adb', '-L', f'tcp:localhost:{port}', 'server', 'nodaemon'],
                                  stdout=log, stderr=subprocess.STDOUT,
                                  env=dict(os.environ, ADB_TRACE='usb'))
        try:
            time.sleep(0.5)
            client = ['adb', '-P', port, '-s', serial]
            deadline = time.monotonic() + 180
            last_status = None
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError(f'Owned ADB server exited ({server.returncode})')
                if 'USBDEVFS_CLAIMINTERFACE) failed: Device or resource busy' in Path('.local/phone-adb.log').read_text():
                    raise RuntimeError('USB interface is already claimed; release the other device session first')
                state = subprocess.run([*client, 'get-state'], capture_output=True, timeout=5)
                if state.stdout.strip() == b'device':
                    break
                status = state.stderr.decode(errors='replace').strip()
                if status != last_status:
                    print(status, file=log, flush=True)
                    last_status = status
                time.sleep(1)
            else:
                raise RuntimeError('Phone not authorized or unavailable; check its USB debugging prompt')
            actual = subprocess.check_output([*client, 'get-serialno'], text=True).strip()
            if actual != serial:
                raise RuntimeError('Unexpected phone identity')
            print('Configured phone connected through isolated ADB', flush=True)
            return subprocess.run(sys.argv[1:], env=dict(os.environ, ANDROID_SERIAL=serial)).returncode
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == '__main__':
    sys.exit(main())
