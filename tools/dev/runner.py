#!/usr/bin/env python3
"""Launch project-owned tools in disposable Linux namespaces.

Installation choices and device identifiers are read from ignored local config.
No host SDK, tool cache, Git credentials, ADB server or session socket is mounted.
"""
import json
import fcntl
import os
from pathlib import Path
import resource
import select
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.toolchains'
UTILITIES = ('bash', 'sh', 'env', 'cat', 'uname', 'dirname', 'basename', 'ls',
             'sed', 'find', 'xargs', 'mkdir', 'cp', 'mv', 'rm', 'chmod', 'tar',
             'gzip', 'xz', 'unzip', 'zip', 'curl', 'git', 'readlink', 'realpath',
             'cut', 'tr', 'head', 'tail', 'sort', 'sha256sum', 'id', 'date',
             'touch', 'ln', 'true', 'false', 'sleep', 'du', 'df', 'tee', 'awk',
             'grep', 'expr', 'getconf', 'wc', 'od', 'cmp', 'timeout', 'echo')


def config():
    value = json.loads((ROOT / '.local/dev.json').read_text())
    if value['adb_port'] == 5037 or not 1024 <= value['adb_port'] <= 65535:
        raise ValueError('Use an explicit, non-default ADB port')
    port = value['emulator_port']
    if port % 2 or not 5554 <= port <= 5682:
        raise ValueError('Invalid emulator console port')
    if not value['avd'].replace('_', '').isalnum():
        raise ValueError('Invalid AVD name')
    return value


def prepare():
    for name in ('home', 'gradle', 'android/user', 'android/avd', 'android/sdk',
                 'cache', 'config', 'data', 'run', 'tmp', 'downloads',
                 'mise/data', 'mise/cache', 'mise/config', 'mise/state'):
        path = STATE / name
        if not path.resolve().is_relative_to(ROOT):
            raise ValueError('Project state must not link outside this checkout')
        path.mkdir(parents=True, exist_ok=True)


def environment(cfg, mode):
    sdk = STATE / 'android/sdk'
    return {
        'HOME': os.environ['HOME'],  # Same value, backed by this project's private mount.
        'PATH': ':'.join(str(p) for p in (
            ROOT / 'tools/dev/bin', STATE / 'jdk17/bin', STATE / 'python/bin', STATE / 'mise/bin',
            sdk / f"cmdline-tools/{cfg['versions']['android-sdk']}/bin", sdk / 'platform-tools',
            sdk / 'emulator', Path('/usr/bin'))),
        'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TZ': 'UTC',
        'JAVA_HOME': str(STATE / 'jdk17'),
        'ANDROID_HOME': str(sdk), 'ANDROID_SDK_ROOT': str(sdk),
        'ANDROID_USER_HOME': str(STATE / 'android/user'),
        'ANDROID_EMULATOR_HOME': str(STATE / 'android/user'),
        'ANDROID_AVD_HOME': str(STATE / 'android/avd'),
        'ANDROID_ADB_SERVER_PORT': str(cfg['adb_port']),
        'ADB_SERVER_SOCKET': f"tcp:127.0.0.1:{cfg['adb_port']}",
        # The legacy Linux backend enumerates only the explicitly mounted USB node.
        # libusb additionally assumes a complete host sysfs tree.
        'ADB_LIBUSB': '0',
        'GRADLE_USER_HOME': str(STATE / 'gradle'),
        'XDG_CACHE_HOME': str(STATE / 'cache'),
        'XDG_CONFIG_HOME': str(STATE / 'config'),
        'XDG_DATA_HOME': str(STATE / 'data'),
        'XDG_RUNTIME_DIR': '/run/user', 'TMPDIR': '/tmp',
        **{f'MISE_{name.upper()}_DIR': str(STATE / 'mise' / name)
           for name in ('data', 'cache', 'state', 'config')},
        'MISE_CEILING_PATHS': str(ROOT), 'MISE_YES': '1',
        'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
        'GIT_TERMINAL_PROMPT': '0', 'PYTHONDONTWRITEBYTECODE': '1',
        'JAVA_TOOL_OPTIONS': '-XX:ActiveProcessorCount=4',
        'NEXTBOARD_SANDBOX': mode,
    }


def sandbox_args(cfg, mode, run_dir, info_fd, command):
    args = ['/usr/bin/bwrap', '--unshare-all', '--die-with-parent',
            '--new-session', '--cap-drop', 'ALL', '--clearenv',
            '--hostname', 'android-project', '--proc', '/proc', '--dev', '/dev',
            '--tmpfs', '/tmp', '--dir', '/run/user', '--chmod', '0700', '/run/user',
            '--ro-bind', '/usr/lib', '/usr/lib', '--symlink', 'usr/lib', '/lib',
            '--symlink', 'usr/lib', '/lib64', '--symlink', 'lib', '/usr/lib64',
            '--dir', '/usr/bin', '--symlink', 'usr/bin', '/bin',
            '--bind', str(STATE / 'home'), os.environ['HOME'],
            '--bind', str(ROOT), str(ROOT), '--chdir', str(ROOT)]
    for name in UTILITIES:
        path = Path('/usr/bin') / name
        if path.exists():
            args += ['--ro-bind', str(path), str(path)]
    for path in ('/etc/ssl', '/etc/ca-certificates', '/usr/share/ca-certificates', '/usr/share/fonts',
                 '/etc/fonts'):
        if Path(path).exists():
            args += ['--ro-bind', path, path]
    for name in ('.git', '.agents', '.codex', '.aws'):
        path = ROOT / name
        if path.exists():
            args += ['--tmpfs', str(path), '--remount-ro', str(path)]
    for name, content in {'hosts': '127.0.0.1 localhost\n',
                          'passwd': f"project:x:{os.getuid()}:{os.getgid()}::{os.environ['HOME']}:/bin/bash\n",
                          'group': f'project:x:{os.getgid()}:\n',
                          'nsswitch.conf': 'passwd: files\ngroup: files\nhosts: files dns\n',
                          'resolv.conf': 'nameserver 10.0.2.3\n'}.items():
        path = run_dir / name
        path.write_text(content)
        args += ['--ro-bind', str(path), f'/etc/{name}']
    if mode == 'phone':
        phone = cfg['phone']
        node = Path(phone['usb_node'])
        if node.parent.parent != Path('/dev/bus/usb') or not stat.S_ISCHR(node.stat().st_mode):
            raise ValueError('Expected one USB device node')
        device = node.stat().st_rdev
        sysfs = Path(f'/sys/dev/char/{os.major(device)}:{os.minor(device)}').resolve()
        if (sysfs / 'serial').read_text().strip() != phone['serial']:
            raise ValueError('USB device identity changed; update local configuration')
        args += ['--dev-bind', str(node), str(node), '--ro-bind', str(sysfs), str(sysfs),
                 '--dir', '/sys/dev/char', '--symlink', str(sysfs),
                 f'/sys/dev/char/{os.major(device)}:{os.minor(device)}',
                 '--dir', '/sys/bus/usb/devices', '--symlink', str(sysfs),
                 f'/sys/bus/usb/devices/{sysfs.name}']
    if mode == 'device':
        if not os.access('/dev/kvm', os.R_OK | os.W_OK):
            raise RuntimeError('KVM is unavailable; accelerated device testing is required')
        args += ['--dev-bind', '/dev/kvm', '/dev/kvm']
    for name, value in environment(cfg, mode).items():
        args += ['--setenv', name, value]
    args += ['--info-fd', str(info_fd), '--', str(STATE / 'python/bin/python3'),
             '-I', 'tools/dev/inside.py', str(run_dir), *command]
    return args


def limits():
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:4])
    # Per-process address-space bound, not an aggregate memory guarantee.
    resource.setrlimit(resource.RLIMIT_AS, (12 * 1024**3, 12 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.nice(5)


def launch(mode, command):
    cfg = config()
    prepare()
    device_lock = None
    if mode in ('device', 'phone'):
        device_lock = (STATE / f'{mode}.lock').open('w')
        try:
            fcntl.flock(device_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            device_lock.close()
            raise RuntimeError('This project already has an active session for that device profile')
    network = None
    child = None
    network_lifetime = None
    with tempfile.TemporaryDirectory(prefix='sandbox-', dir=STATE / 'run') as directory:
        run_dir = Path(directory)
        with (run_dir / 'namespace.json').open('w+') as info:
            args = sandbox_args(cfg, mode, run_dir, info.fileno(), command)
            try:
                child = subprocess.Popen(args, pass_fds=(info.fileno(),), preexec_fn=limits)
                if mode == 'download':
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        info.seek(0)
                        try:
                            pid = json.load(info)['child-pid']
                            break
                        except (ValueError, KeyError):
                            if child.poll() is not None:
                                return child.returncode
                            time.sleep(0.05)
                    else:
                        raise RuntimeError('Sandbox namespace did not become ready')
                    ready_read, ready_write = os.pipe()
                    exit_read, network_lifetime = os.pipe()
                    with open(f'/proc/{pid}/ns/net', 'rb') as netns:
                        # NS_GET_USERNS: --dev makes bwrap nest its final user namespace.
                        # slirp must enter the namespace which actually owns the network.
                        owner_fd = fcntl.ioctl(netns, 0xb701)
                    try:
                        network = subprocess.Popen([
                            '/usr/bin/slirp4netns', '--configure', '--disable-host-loopback',
                            '--enable-seccomp',
                            '--userns-path', f'/proc/self/fd/{owner_fd}',
                            '--exit-fd', str(exit_read),
                            '--ready-fd', str(ready_write), str(pid), 'tap0',
                        ], pass_fds=(ready_write, owner_fd, exit_read), stdout=subprocess.DEVNULL)
                        os.close(ready_write)
                        ready_write = None
                        if not select.select([ready_read], [], [], 15)[0] or not os.read(ready_read, 1):
                            raise RuntimeError('Isolated download networking failed')
                    finally:
                        os.close(owner_fd)
                        os.close(exit_read)
                        os.close(ready_read)
                        if ready_write is not None:
                            os.close(ready_write)
                (run_dir / 'ready').touch()
                return child.wait()
            finally:
                if network_lifetime is not None:
                    os.close(network_lifetime)
                for process in (network, child):
                    if process is not None and process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()


def main():
    os.umask(0o077)
    args = sys.argv[1:]
    if not args:
        raise SystemExit('Usage: ./dev {setup|check|build|test|download|device|phone|--} [command ...]')
    action, *args = args
    mode = 'offline'
    if action == 'setup':
        mode, command = 'download', ['python3', '-I', 'tools/dev/setup.py']
    elif action == 'check':
        command = ['python3', '-I', 'tools/dev/check.py']
    elif action in ('build', 'test'):
        tasks = [':app:assembleDebug', ':app:assembleRelease'] if action == 'build' else [
            ':app:testDebugUnitTest', '--tests', 'helium314.keyboard.latin.nextword.*']
        command = ['./gradlew', '--offline', '--no-daemon', '--max-workers=2',
                   '-Dorg.gradle.vfs.watch=false', '-Pkotlin.compiler.execution.strategy=in-process',
                   *tasks, *args]
    elif action in ('download', 'device', 'phone', '--'):
        mode = action if action != '--' else 'offline'
        if args and args[0] == '--':
            args.pop(0)
        if not args:
            raise SystemExit('An explicit command is required')
        command = (['python3', '-I', f'tools/dev/{action}.py', *args]
                   if action in ('device', 'phone') else args)
    else:
        raise SystemExit('Unknown command')
    return launch(mode, command)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        sys.exit(str(error))
