# AGENTS.md — NextBoard (HeliBoard fork + offline next-word prediction)

You are the Android dev agent for NextBoard. Full implementation brief: **NEXTWORD_SPEC.md** in this repo root. Read it completely before writing any code. The spec's integration points were verified against upstream master; treat it as authoritative over your own assumptions about HeliBoard internals.

## Environment (do not change these)
- Repo root: this directory. Fork of Helium314/HeliBoard; remote `upstream` = Helium314/HeliBoard (public, read-only), and remote `origin` = `git@github.com:ake-khada/NextBoard.git` using a repo-scoped deploy key. `origin` and all credentialed Git operations are reserved for the human, who reviews and manually pushes changes. Never push, fetch from `origin`, or otherwise use its credentials. Work on branch `nextword`.
- SDK: `$ANDROID_HOME` = `~/android-sdk` (compileSdk 36, JDK 17 = system Java, already correct).
- **`ANDROID_ADB_SERVER_PORT=5038` is set in the shell profile. Never unset it, never use port 5037, never `adb kill-server` without the env var active.** Port 5037 belongs to a different project owned by another user. You must never see or touch its devices.
- Emulator AVD: `NextBoard_API36`. The user's physical phone is never available to you; emulator only.

## Commands
```bash
# emulator (headless, deterministic)
$ANDROID_HOME/emulator/emulator -avd NextBoard_API36 \
  -no-window -no-audio -no-snapshot -no-boot-anim -gpu swiftshader_indirect &
adb wait-for-device
adb shell 'while [ "$(getprop sys.boot_completed)" != "1" ]; do sleep 2; done'

# build / install
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/*.apk

# enable + activate the IME (debug applicationId has .debug suffix)
adb shell ime enable helium314.keyboard.debug/helium314.keyboard.latin.LatinIME
adb shell ime set    helium314.keyboard.debug/helium314.keyboard.latin.LatinIME
# if the component name is rejected, resolve it with: adb shell ime list -a

# logs
adb logcat -s NextWord:V AndroidRuntime:E
```

## Hard rules
1. Diff surface to existing implementation files is exactly three changes: one guarded block in `app/src/main/java/helium314/keyboard/latin/DictionaryFacilitatorImpl.kt`, `noCompress += "nwlm"` in `app/build.gradle.kts`, and `signingConfig = signingConfigs.getByName("debug")` inside `buildTypes.release`. The release signing line exists only for locally testable release builds and must be replaced by a real keystore before any public distribution. Everything else is new files under `.../latin/nextword/`, `app/src/main/assets/nextword/`, and `tools/lm/`.
2. Never add the INTERNET permission or any network-touching dependency. Never add ONNX, TF, llama.cpp, or any native code.
3. Never modify autocorrect behavior. Predictions are `KIND_PREDICTION` only.
4. One fix per commit, small commits, imperative messages. Never run `git push`, `git fetch origin`, or any credentialed Git command; `origin` is reserved for the human's manual publishing workflow. Never rewrite history on `nextword` — no rebase, no `git commit --amend`, no reset of committed work. Treat every commit as published the moment it is made; if a commit was wrong, fix it with a new commit.
5. Keep the branch rebase-friendly against `upstream/master` (small, well-separated commits). Do not perform the rebase yourself; the human decides when and does it from the mirror. If upstream drifted since the spec, adapt at the named classes/functions, not by expanding the diff surface.
6. Stay inside this repo, `~/android-sdk`, `~/.android`, and `~/.gradle`. Do not read or write anything else in the filesystem, especially other users' homes.
7. Model files must come out of `tools/lm/build_model.py` deterministically (sorted iteration, fixed seed). Run `tools/lm/eval_model.py` and report the top-1/top-3 hit rates before declaring a model done. Gates are in the spec.

## Definition of done for the agent loop
- JVM unit tests for the `.nwlm` reader pass (generate a tiny fixture model via `tools/lm/build_model.py --tiny`).
- `assembleDebug` clean; installs; IME activates; logcat shows the model-load marker for en/fr/ru with load time < 10 ms; no crashes while typing via `adb shell input keyevent` smoke sequence.
- Typing-quality and gesture validation is done by the human on a real device. Do not simulate it with scripted taps or swipes and do not claim it passed.

## Reporting
After each work session: what changed, commit hashes, current eval numbers, open risks — appended to `PROGRESS.md` (committed). The human reads PROGRESS.md from the mirror; write it for a reader who did not watch the session.
