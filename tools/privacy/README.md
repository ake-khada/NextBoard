# Commit privacy

Public changes contain application code and generic reusable project tools and
documentation. Internal instructions, plans, session reports, environment details,
device records, tool installations, signing material, and diagnostic artifacts
stay in ignored local files. Ignored records need separate private backups.

`check_public_tree.py` checks the complete index and non-ignored working files.
It reports locations and rule names without printing matched values. It rejects
local-only paths even when force-added, recognizes common private metadata and
secret formats, and checks an optional ignored `.privacy-local-patterns` file.
Put one private literal per line in that file; empty lines and comments are skipped.
Do not commit the denylist itself. Tests use synthetic identifiers only.

The Git hooks check exact staged blobs, effective author/committer identities,
and commit messages. Configure a GitHub noreply email locally. The pre-commit hook
also runs the project's own Gitleaks binary against the staged diff with full
redaction. Neither detector guarantees that all private data is absent; review
the proposed files and message as well.
The message hook also scans the message for secrets. The existing upstream IDE
formatting rules and source templates are retained; their contents are still
checked, and unrelated IDE state is rejected.

Provision independent pinned tools under `.toolchains/python` (Python 3.14.7)
and `.toolchains/gitleaks` (Gitleaks 8.30.1). Hooks fail closed when these are absent.
After checking any existing hook configuration, enable them for this checkout:

```sh
git config --local core.hooksPath tools/git-hooks
.toolchains/python/bin/python3 -B tools/privacy/check_public_tree.py --commit-identities
.toolchains/python/bin/python3 -B -m unittest discover -s tools/privacy/tests -v
```

These hooks are local configuration and must be enabled in each checkout. They
do not publish changes or modify other projects.

Ignoring or untracking a file does not erase its older commits. Removing private
information from earlier history requires a separately authorized, scoped rewrite
and coordination for any copies already published. Do not publish backup refs,
local patches, or old stashes after a cleanup.
