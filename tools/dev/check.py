"""Executable negative checks for the effective offline sandbox, without host probes."""
import os
from pathlib import Path
import shutil
import socket
import subprocess

root = Path.cwd()
state = root / '.toolchains'
assert os.environ['NEXTBOARD_SANDBOX'] == 'offline'
assert os.environ['ANDROID_ADB_SERVER_PORT'] != '5037'
for name in ('python3', 'java', 'emulator'):
    path = shutil.which(name)
    assert path and Path(path).resolve().is_relative_to(state), name
for name in ('GRADLE_USER_HOME', 'ANDROID_HOME', 'ANDROID_USER_HOME', 'ANDROID_AVD_HOME',
             'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'MISE_DATA_DIR', 'MISE_CACHE_DIR'):
    assert Path(os.environ[name]).resolve().is_relative_to(state), name
assert 'SSH_AUTH_SOCK' not in os.environ
assert 'DBUS_SESSION_BUS_ADDRESS' not in os.environ
assert not Path('/run/host').exists()
assert not Path('/dev/bus/usb').exists()
assert not Path('/dev/kvm').exists()
assert not any((root / '.git').iterdir())
assert not Path('/sys').exists()
assert len(os.sched_getaffinity(0)) <= 4
assert Path(shutil.which('adb')).resolve() == root / 'tools/dev/bin/adb'
assert subprocess.run(['adb', '-P', '5037', 'devices'], capture_output=True).returncode != 0
# No default route in this new network namespace. No socket reaches the host.
routes = Path('/proc/net/route').read_text().splitlines()[1:]
assert not routes, routes
with socket.socket() as test:
    test.settimeout(0.1)
    assert test.connect_ex(('192.0.2.1', 443)) != 0
print('PASS: owned tools/state, hidden credentials/devices, private networking, bounded CPU')
subprocess.run(['java', '-version'], check=True)
