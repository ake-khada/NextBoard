The `dev` launcher runs project-owned Android tools in disposable Linux
namespaces. Installation pins, SDK package choices, ports, AVD names and optional
phone identities belong in ignored `.local/dev.json`. Keep that configuration and
installation records in private backups. This directory contains reusable code,
not a machine configuration.

The launcher requires bubblewrap, slirp4netns, Linux user namespaces and a project
Python at `.toolchains/python/bin/python3`. Provision Python and mise independently
into `.toolchains/`; never point these directories at another installation.
`./dev setup` uses that mise to install the configured JDK, SDK tools and packages.
The configuration has `versions` entries for `java`, `python`, `gitleaks` and
`android-sdk`, plus `sdk_packages`, `adb_port`, `emulator_port` and `avd`.
Use `sdk_revisions` to check exact installed package revisions. Setup installs
missing SDK packages and rejects revision mismatches instead of updating installed
packages implicitly. Google's SDK repository must still provide the requested
revision for a fresh installation to reproduce that pin.
Device testing requires KVM. No global shell or SDK settings are changed.

Commands:

* `./dev setup`: download tools and accept SDK licences in this project's SDK.
* `./dev download COMMAND ...`: explicitly allow dependency downloads.
* `./dev build`: build debug and locally signed release APKs offline.
* `./dev test`: execute the next-word JVM test selection offline. Add
  `--rerun-tasks` to force execution rather than reuse Gradle results.
* `./dev check`: check effective tool, cache, device and network isolation.
* `./dev -- COMMAND ...`: run another command in the offline build profile.
* `./dev device COMMAND ...`: boot the configured emulator, run the command and
  stop its emulator and ADB processes. This profile has no outbound network.
* `./dev phone COMMAND ...`: use one explicitly authorized phone. Local `phone`
  configuration must contain its exact `serial` and current `usb_node`. Only that
  node and its sysfs identity are exposed; the identity is checked before launch.
  `--diagnose COMMAND ...` runs inside that same profile without starting ADB.

Device commands receive `ANDROID_SERIAL` and `ANDROID_ADB_SERVER_PORT`. Pass both
explicitly to ADB, for example:

```bash
adb -P "$ANDROID_ADB_SERVER_PORT" -s "$ANDROID_SERIAL" shell getprop ro.build.version.sdk
```

An optional `device_preflight` in local configuration runs inside the device
sandbox before launch, with a three-minute deadline. When present, it must be a
nonempty list of strings with a nonempty executable argument. Omit the field to
skip this check. Invalid configuration or a failed check prevents ADB and emulator
launch. Use it for local maintenance checks. Device commands also receive the
namespace-local `NEXTBOARD_ADB_PID` and `NEXTBOARD_EMULATOR_PID` of their owned
lifecycle processes, allowing maintenance tools to verify process ownership.

The ADB wrapper rejects a default port, foreign target, remote connection, and
unmanaged server lifecycle. Every device session has its own network namespace;
its loopback sockets cannot reach host ADB services. Servers are stopped by their
owned process handles, never by a global `kill-server`. A physical phone's USB
interface remains exclusive hardware: another server must release that interface
before this one can use it. Closing an app window does not necessarily stop ADB.
Do not clear app data, uninstall an existing app, or replace its signing key to
work around an installation mismatch.

The filesystem exposes the checkout, its private home and state, selected shell
utilities, read-only OS runtime libraries/certificates/fonts, and private `/tmp`
and `/proc`. Git metadata and agent credential directories are masked. Host home
files, other projects, session sockets and broad USB access are not mounted. HOME
keeps its original value but resolves to the project's private home mount.

The download profile uses slirp with host-loopback access disabled. It has
outbound network access, including potentially reachable LAN services; use it
only for deliberate downloads. Normal build and device profiles have no route
out. The slirp helper is a host sandbox facility with seccomp, and exits with the
launcher. CPU affinity is limited to four cores, Gradle uses two workers, and
each process has a 12 GiB address-space limit. These are not an aggregate memory
quota or a guarantee against resource contention.

Run `.toolchains/python/bin/python3 -I tools/dev/test_isolation.py` to exercise
real namespaces with synthetic foreign files and an ephemeral host listener.
Run `./dev -- python3 -I tools/dev/test_device.py` for preflight and identity checks.
Run the privacy gate before staging. Never commit local configuration, keys,
device records, logs, screenshots or performance measurements. The existing
release signing configuration is for local testing, not public distribution.
