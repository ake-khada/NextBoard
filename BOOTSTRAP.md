# BOOTSTRAP.md — one-time environment + repo setup (phase 0)

Execute top to bottom as user nextboard on macOS (Apple Silicon). Rules for this phase:
- No sudo. Nothing here needs it. If a step appears to need sudo, STOP and report instead.
- Stay inside $HOME. Never touch ADB port 5037 or any device on it; this account's ADB universe is port 5038 only.
- Idempotency: any step whose result already exists (directory, remote, branch, AVD, commit) counts as done — verify it and move on. Re-running this file must always be safe.
- If a verification fails, fix the environment and retry; do not improvise alternative architectures.

## 0. Preconditions
- JDK 17 resolves: /usr/libexec/java_home -v 17
  If it does not resolve, STOP and report; a human/admin must install it. Do not attempt to install a JDK.
- git is available (Xcode command line tools are machine-wide).

## 1. Shell environment
Append to ~/.zshrc (skip any line already present), then apply the same exports to the current session:
  export ANDROID_HOME=$HOME/android-sdk
  export PATH=$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH
  export ANDROID_ADB_SERVER_PORT=5038

## 2. Android SDK
  mkdir -p ~/android-sdk/cmdline-tools && cd ~/android-sdk/cmdline-tools
  curl -LO https://dl.google.com/android/repository/commandlinetools-mac-14742923_latest.zip
  unzip -q commandlinetools-mac-*.zip && mv cmdline-tools latest && rm commandlinetools-mac-*.zip
  yes | sdkmanager --licenses
  sdkmanager "platform-tools" "emulator" "platforms;android-36" "system-images;android-36;google_apis;arm64-v8a"
  avdmanager create avd -n NextBoard_API36 -k "system-images;android-36;google_apis;arm64-v8a" -d pixel_6
Note: the zip extracts to cmdline-tools/ and MUST be renamed to cmdline-tools/latest/ or sdkmanager refuses to run.
Do not install build-tools manually; Gradle fetches the pinned version on first build.
Verify: "adb devices" starts a fresh server (port 5038 via the env var) and lists no devices; "emulator -list-avds" prints NextBoard_API36.

## 3. Repo
If ~/NextBoard does not exist: git clone https://github.com/Helium314/HeliBoard.git ~/NextBoard
Then, in ~/NextBoard, ensure each of the following (check first, act only if missing):
  remote "upstream" = https://github.com/Helium314/HeliBoard.git (rename origin to upstream if the clone is fresh)
  NO other remotes. This account has no GitHub credentials and never will. The human mirrors this repo from another account and handles all pushing/pulling with GitHub there.
  current branch = nextword (create it if absent)
  git config user.name "nextboard-agent"
  git config user.email "nextboard-agent@users.noreply.github.com"
Docs: AGENTS.md and NEXTWORD_SPEC.md must end up in the repo root. Search in order, move from the first location that has them:
  1. already in the repo root (done, skip)
  2. the home directory: ~/AGENTS.md and ~/NEXTWORD_SPEC.md (their current location)
  3. ~/nextboard-docs/
If found in none of these, STOP and report; the human must restore them.
Copy ~/BOOTSTRAP.md into the repo root as well, then commit whatever docs are uncommitted:
  git add AGENTS.md NEXTWORD_SPEC.md BOOTSTRAP.md && git commit -m "docs: agent brief, implementation spec, bootstrap"
NEVER run git push. The only permitted network git operation is fetching from upstream (public, read-only). All work is local commits on branch nextword; publishing is the human's job, done from their mirror.

## 4. Baseline proof (unmodified upstream code)
Using the exact commands in AGENTS.md: boot the headless emulator, run ./gradlew :app:assembleDebug, install the APK, enable and set the IME, and confirm it is listed by "adb shell ime list -s". The first Gradle run downloads the wrapper and dependencies; that is expected.
Any failure here is an environment problem. Fix the environment; do NOT modify repository code to make the baseline pass.

## 5. Handoff to implementation
- Create PROGRESS.md; record bootstrap results: tool versions, emulator boot OK, baseline build/install/IME OK, timings. Commit it.
- Read AGENTS.md and NEXTWORD_SPEC.md in full. Then begin implementation in this order: tools/lm pipeline with --tiny fixture, the .nwlm reader plus JVM unit tests, and only then the HeliBoard integration block. This keeps early commits pure-new-files and independently testable.
- Corpus downloads for tools/lm: cap total downloads at roughly 2 GB. A few million sentences per language is more than enough for models capped at 3 MB. Record exact sources, URLs, and sizes in tools/lm/README.md.
- Future Codex sessions must be launched from ~/NextBoard so AGENTS.md is picked up automatically. This BOOTSTRAP.md is complete once PROGRESS.md exists; do not re-run it.
