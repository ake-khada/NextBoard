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
