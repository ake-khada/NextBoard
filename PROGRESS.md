# NextBoard progress

## 2026-07-16 — Bootstrap and upstream baseline

### Completed

- Configured `ANDROID_HOME=/Users/nextboard/android-sdk`, Android SDK paths, and the isolated `ANDROID_ADB_SERVER_PORT=5038` in `/Users/nextboard/.zshrc`.
- Installed Android command-line tools 20.0, platform-tools 37.0.0, Android Emulator 36.6.11, Android platform 36, the Google APIs Android 36 ARM64 system image revision 7, Gradle-pinned Build Tools 35.0.0, and NDK 28.0.13004108.
- Created and cold-booted the `NextBoard_API36` ARM64 AVD. The measured ADB boot-completion wait was 9 seconds after the emulator process passed host checks.
- Cloned upstream HeliBoard at `84614762199c9574cd0fac1dd41da48e7616b3f2`, renamed the sole remote to `upstream`, created branch `nextword`, and configured the repository author.
- Committed the agent brief, implementation spec, and bootstrap instructions as `9ea41e30448464aacf99e6c95da6ce8263df348d`.
- Built the unmodified upstream application with `./gradlew :app:assembleDebug`: success in 59 seconds after dependency installation.
- Installed the debug APK, enabled and selected `helium314.keyboard.debug/helium314.keyboard.latin.LatinIME`, and confirmed it in `adb shell ime list -s`: success in 1 second.

### Tool versions

- macOS 26.5.1, Apple Silicon (`aarch64`)
- Eclipse Temurin JDK 17.0.19
- Git 2.50.1 (Apple Git-155)
- Gradle 8.14; Kotlin 2.0.21
- Android SDK command-line tools 20.0
- Android Debug Bridge 1.0.41 / platform-tools 37.0.0
- Android Emulator 36.6.11

### Evaluation

- Next-word model evaluation has not started; there are no top-1 or top-3 figures yet.

### Open risks and environment notes

- The managed execution sandbox blocks the emulator's ARM feature `sysctl` probe. Launch the emulator with approved escalated execution; the exact headless command then boots successfully on ADB port 5038.
- The JVM defaults `java.io.tmpdir` to a sandbox-protected macOS directory. Set `JAVA_TOOL_OPTIONS=-Djava.io.tmpdir=/private/tmp` for Gradle commands in managed sessions.
- This session verified only the unmodified upstream baseline. No NextBoard implementation code or model assets exist yet.

## 2026-07-16 — Offline next-word models and emulator validation

### Completed

- Added deterministic, dependency-free model build and held-out evaluation tools. The tokenizer, key normalization, fixed-seed partition, xxHash64 implementation, pruning, and packed little-endian `.nwlm` writer are shared by the tools.
- Added the memory-mapped Kotlin reader, strict format validation, trigram-to-bigram backoff, normalization, sensitive-context rejection, per-language asset cache, and `KIND_PREDICTION` conversion.
- Integrated static predictions in the specified empty-composing path. The only modified upstream source files are the guarded block in `DictionaryFacilitatorImpl.kt` and the `.nwlm` `noCompress` declaration in `app/build.gradle.kts`.
- Added a runtime input-type guard for password, email, and URI fields after emulator validation showed that upstream blocks password/no-suggestion fields but can still request ordinary suggestions for URI/email fields.
- Bundled evaluated English, French, and Russian models. All three were independently rebuilt from their documented snapshots and matched byte-for-byte with `cmp`.
- Documented the official OPUS OpenSubtitles v2016 archive URLs, archive and snapshot hashes, corpus sizes, split seed, and exact commands in `tools/lm/README.md`. The two downloaded archives total 1,508,876,295 bytes; each production model uses exactly 10,000,000 non-held-out sentences.
- Updated `AGENTS.md` for the human-only `origin` publishing workflow. No push, `origin` fetch, or credentialed Git command was run.
- Cleared the synthetic score-calibration data, installed the final clean APK on `emulator-5554` through isolated ADB port 5038, enabled HeliBoard, and left `helium314.keyboard.debug/helium314.keyboard.latin.LatinIME` selected.

### Commits

- `50c16835` — deterministic model tools
- `691a166c` — memory-mapped reader and JVM tests
- `5beed73a` — suggestion integration and uncompressed assets
- `62a39300` — human-only `origin` workflow
- `1595e755` — evaluated production models and corpus documentation
- `62e47d5a` — password/email/URI field suppression

### Production evaluation

Each row is the fixed-seed `--holdout-modulus 200` partition evaluated over 50,000 held-out sentences.

| Language | Model bytes | Top-1 | Top-3 | Coverage | Events | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| en | 2,784,269 | 16.6249% | 28.4482% | 97.9656% | 274,678 | pass (>= 28%) |
| fr | 2,793,815 | 15.7507% | 27.3222% | 97.5323% | 256,268 | pass (>= 22%) |
| ru | 2,843,773 | 13.8996% | 23.1018% | 94.6575% | 245,877 | pass (>= 22%) |

Model SHA-256 values are:

- en: `116735ce9bc378f05fd97ffdf365f7d16b69823b5513dd44a72955ed68425855`
- fr: `eb4795692ddd1d4488dfbb813483f0902536164b3c22872491c2ff4bd12a3235`
- ru: `189cb7f07c943970f5a35ce9ce2efed9291be3428d9db4b40ca1fa091ca50f4e`

### Validation evidence

- Final clean command: `./gradlew clean :app:testDebugUnitTest --tests helium314.keyboard.latin.nextword.NextWordModelTest :app:assembleDebug` — success in 32 seconds. All four reader tests passed with zero failures or errors.
- The final APK is 35,397,762 bytes. A clean build of baseline commit `84614762` is 26,968,993 bytes, so growth is 8,428,769 bytes, below the 9 MB gate. The three model payloads total 8,421,857 bytes and `unzip -lv` reports each as `Stored`.
- The final manifest has no `INTERNET` permission. The temporary field-test activity and calibration logging were removed before the final clean build.
- Cold emulator model mappings were en 0.315 ms, fr 0.278 ms, and ru 2.624 ms; all are below 10 ms. After the final clean install and data reset, en mapped in 0.255 ms.
- Shell key-event smoke input completed with no `AndroidRuntime` errors. Direct production-model probes returned `be/see/go` for `I want to`, `te/vous/le` for `je vais`, candidates for the elided `j’ai` context, and `чтобы/сказать/знать` for `я хочу`. Russian `все` and `всё` produced identical lookup results.
- Runtime field probes loaded the model for a normal text field and produced no model-load or crash entry for email, URI, or password fields. Setting the existing `next_word_prediction` preference to false likewise prevented model loading in a normal text field.
- Mandatory score calibration used the real `TYPE_USER_HISTORY` dictionary in a temporary debug build. A learned prediction scored 251; static candidates in the same log dump scored 81–83 and the single static ceiling remains 96, leaving personalization above the static band. Calibration instrumentation and its synthetic entry are absent from the final build/device data.
- The diff from baseline modifies exactly the two permitted existing implementation files. All other implementation and test paths are new, and `git diff --check` plus repository connectivity checks pass.

### Open risks and human validation

- Real-device typing quality, suggestion selection, backspace behavior after accepting a prediction, sentence-start presentation, and gesture-adjacent behavior still require the human checks mandated by `AGENTS.md`. No scripted taps or swipes were used and no real-device quality claim is made.
- The large OpenSubtitles snapshots remain outside Git by design. Rebuilding the production assets requires reacquiring the two documented archives and reproducing the documented snapshot prefixes.
