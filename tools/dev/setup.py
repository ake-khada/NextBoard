"""Download independent tools; invoked only in the download sandbox."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import re

root = Path.cwd()
state = root / '.toolchains'
cfg = json.loads((root / '.local/dev.json').read_text())
if os.environ.get('NEXTBOARD_SANDBOX') != 'download':
    raise RuntimeError('Tool installation requires the download sandbox')
mise = state / 'mise/bin/mise'
for name, destination, executable in (
    ('java', 'jdk17', 'bin/java'), ('python', 'python', 'bin/python3'),
    ('gitleaks', 'gitleaks', 'gitleaks'),
):
    target = state / destination
    if not (target / executable).exists():
        subprocess.run([str(mise), 'install-into', f"{name}@{cfg['versions'][name]}", str(target)], check=True)

sdk = state / 'android/sdk'
sdkmanager = sdk / f"cmdline-tools/{cfg['versions']['android-sdk']}/bin/sdkmanager"
if not sdkmanager.exists():
    staging = state / 'android/cli'
    if not (staging / 'cmdline-tools').exists():
        subprocess.run([str(mise), 'install-into', f"android-sdk@{cfg['versions']['android-sdk']}", str(staging)], check=True)
    shutil.move(str(staging / 'cmdline-tools'), str(sdk / 'cmdline-tools'))
# Licence acceptance is confined to this SDK, never a shared Android installation.
subprocess.run([str(sdkmanager), f'--sdk_root={sdk}', '--licenses'], input=b'y\n' * 100, check=True)
missing = [package for package in cfg['sdk_packages']
           if not (sdk.joinpath(*package.split(';')) / 'source.properties').exists()]
if missing:
    subprocess.run([str(sdkmanager), f'--sdk_root={sdk}', *missing], check=True)
for package, expected in cfg.get('sdk_revisions', {}).items():
    properties = (sdk.joinpath(*package.split(';')) / 'source.properties').read_text()
    actual = re.search(r'^Pkg.Revision\s*=\s*(.+)$', properties, re.MULTILINE)
    if actual is None or actual[1].strip() != expected:
        raise RuntimeError(f'SDK revision differs from local pin: {package}')
