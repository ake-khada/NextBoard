#!/usr/bin/env python3
"""Check publishable files and commit metadata without printing matched values."""

import argparse
import fnmatch
import os
from pathlib import Path
import re
import subprocess
import sys


PRIVATE_PARTS = {
    '.toolchains', '.local', '.agents', '.codex', '.claude', '.worktrees',
    '.android', '.ssh', '.gnupg', '.idea', '.gradle', '.kotlin',
    'audits', 'validation_logs',
}
PRIVATE_NAMES = {
    'AGENTS.md', 'BOOTSTRAP.md', 'NEXTWORD_SPEC.md', 'PROGRESS.md',
    'CLAUDE.md', 'AUDIT_WORKPLAN.md', 'VALIDATION_PROTOCOL.md',
    'local.properties', 'keystore.properties', '.privacy-local-patterns',
    '.DS_Store', 'Thumbs.db', 'Desktop.ini',
}
PRIVATE_GLOBS = (
    '*.local.*', '*.jks', '*.keystore', '*.p12', '*.pfx', '*.pem', '*.key',
    '*.apk', '*.aab', '*.apks', '*.hprof', '*.trace', '*.perfetto-trace',
    'nextboard-*-plan.md', 'nextboard-session-*.md', '._*',
)
# Upstream ships these generic formatting rules and source templates. Their
# contents still pass through every metadata/secret check; no other IDE state is public.
SHARED_IDE_FILES = {
    '.idea/codeStyles/Project.xml', '.idea/codeStyles/codeStyleConfig.xml',
    '.idea/inspectionProfiles/Project_Default.xml',
    *('.idea/fileTemplates/internal/' + name for name in (
        'AnnotationType.java', 'Class.java', 'Enum.java', 'Exception.java',
        'Interface.java', 'Record.java', 'SimpleSourceFile.java',
        'Kotlin Annotation.kt', 'Kotlin Class.kt', 'Kotlin Data Class.kt',
        'Kotlin Enum.kt', 'Kotlin File.kt', 'Kotlin Interface.kt',
        'Kotlin Object.kt', 'Kotlin Sealed Class.kt',
    )),
}
RULES = {
    'personal home path': re.compile(
        rb'(?:/Users/|/home/)[A-Za-z0-9._-]+/|[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\'
    ),
    'literal device serial': re.compile(
        rb'\badb\s+(?:-P\s+\d+\s+)?-s\s+(?!emulator-\d+\b)[A-Za-z0-9][A-Za-z0-9._:-]{7,}'
    ),
    'installation record': re.compile(
        rb'(?:firstInstallTime|lastUpdateTime)\s*[:=]\s*\d{4}-\d\d-\d\d'
    ),
    'private key': re.compile(rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----'),
    'access token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
}


def private_path(path):
    parts = Path(path).parts
    name = parts[-1]
    return (
        (bool(PRIVATE_PARTS.intersection(parts)) and path not in SHARED_IDE_FILES)
        or name in PRIVATE_NAMES
        or ((name == '.env' or name.startswith('.env.')) and name != '.env.example')
        or any(fnmatch.fnmatchcase(name, pattern) for pattern in PRIVATE_GLOBS)
    )


def findings(path, data, local_patterns=()):
    issues = ['local-only file'] if private_path(path) else []
    for number, line in enumerate(data.splitlines(), 1):
        for label, pattern in RULES.items():
            if pattern.search(line):
                issues.append(f'line {number}: {label}')
        if any(pattern.lower() in line.lower() for pattern in local_patterns):
            issues.append(f'line {number}: local denylist')
    return issues


def unsafe_link(path, target):
    target = Path(os.fsdecode(target))
    return target.is_absolute() or '..' in target.parts or private_path(str(Path(path).parent / target))


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)


def check(repo, index_only=False, message=None, identities=False):
    denylist = repo / '.privacy-local-patterns'
    patterns = tuple(
        line.strip() for line in denylist.read_bytes().splitlines()
        if line.strip() and not line.lstrip().startswith(b'#')
    ) if denylist.is_file() else ()
    if message is not None:
        return [f'commit message: {issue}' for issue in findings('MESSAGE', message.read_bytes(), patterns)]

    issues = []
    if identities:
        for name in ('GIT_AUTHOR_IDENT', 'GIT_COMMITTER_IDENT'):
            identity = git(repo, 'var', name)
            issues.extend(f'{name}: {issue}' for issue in findings('IDENTITY', identity, patterns))
            match = re.search(rb'<([^<>]+)>', identity)
            if match is None or not match[1].endswith(b'@users.noreply.github.com'):
                issues.append(f'{name}: use a configured GitHub noreply identity')

    # Read blobs from the index, not their possibly different working copies.
    with subprocess.Popen(
        ['git', '-C', str(repo), 'cat-file', '--batch'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ) as process:
        for entry in filter(None, git(repo, 'ls-files', '--stage', '-z').split(b'\0')):
            metadata, raw_path = entry.split(b'\t', 1)
            mode, oid, stage = metadata.split()
            path = os.fsdecode(raw_path)
            if stage != b'0':
                issues.append(f'index: {path}: unresolved merge')
                continue
            if mode == b'160000':
                issues.append(f'index: {path}: submodule needs separate review')
                continue
            process.stdin.write(oid + b'\n')
            process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3 or header[1] != b'blob':
                raise RuntimeError('Cannot read staged blob')
            data = process.stdout.read(int(header[2]))
            if process.stdout.read(1) != b'\n':
                raise RuntimeError('Incomplete staged blob')
            issues.extend(f'index: {path}: {issue}' for issue in findings(path, data, patterns))
            if mode == b'120000' and unsafe_link(path, data):
                issues.append(f'index: {path}: private or external symlink')
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError('Cannot inspect index')

    if not index_only:
        paths = git(repo, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
        for raw_path in sorted(set(filter(None, paths.split(b'\0')))):
            path = os.fsdecode(raw_path)
            file = repo / path
            if file.is_symlink():
                data = os.fsencode(os.readlink(file))
                if unsafe_link(path, data):
                    issues.append(f'worktree: {path}: private or external symlink')
            elif file.is_file():
                data = file.read_bytes()
            else:
                continue
            issues.extend(f'worktree: {path}: {issue}' for issue in findings(path, data, patterns))
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index-only', action='store_true')
    parser.add_argument('--commit-identities', action='store_true')
    parser.add_argument('--message', type=Path)
    args = parser.parse_args()
    try:
        repo = Path(git(Path.cwd(), 'rev-parse', '--show-toplevel').decode().strip())
        issues = check(repo, args.index_only, args.message, args.commit_identities)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Privacy check could not complete ({type(error).__name__}).', file=sys.stderr)
        return 2
    if issues:
        print('Privacy check failed; matched values are withheld.', file=sys.stderr)
        print('\n'.join(issues), file=sys.stderr)
        return 1
    print('Privacy metadata check passed. Existing history was not scanned or erased.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
