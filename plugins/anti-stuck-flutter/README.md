# Anti-Stuck for Flutter

A Flutter pack for the `anti-stuck` core plugin (installed with it as a dependency). It stops Claude Code sessions
from fighting over the same phone or emulator, keeps Marionette MCP calls from hanging on a backgrounded or paused
app, gives Flutter builds and test suites sensible time limits, and cleans up runaway `flutter_tester` processes.
Documentation and contributing: <https://github.com/toyaji/anti-stuck>.

## What it does

- **`devctl`** — one ledger that every Claude Code session on the machine shares for real devices, emulators and
  heavy builds: `status`, `run <device> [flutter run args]`, `exec <device> -- <cmd>`, `build -- <cmd>` (one at a
  time), `wait <device>`, `release <device>` (the app keeps running for the next session), `stop <device>`, `emu <avd>`
- **Routing** — `flutter run/attach/install/drive/build`, integration tests, `patrol`, `fastlane`, Gradle installs,
  `adb install`/`reboot`/`shell am|pm|input`, `emulator -avd`, `xcrun simctl boot|install|launch…`, and
  `pkill`/`killall` of Flutter or emulator processes are refused unless they go through `devctl`
- **Marionette guard** — before each Marionette MCP call, checks within 3 s that the app's VM answers; blocks
  `connect` when the previously connected app is still running but silent; on Android, requires the app to be in
  the foreground
- **Time limits** — Flutter builds, `pod install`, Gradle, Fastlane and integration tests get longer limits
  (each still needs an `# eta:` line, see the core)
- **Cleanup** — orphaned `flutter_tester` processes, or ones older than 30 min, are killed when a session stops

## What it runs, reads and changes on your machine

- **Runs** `python3` and `sh` scripts from this plugin folder. `devctl` starts `flutter run`, `emulator` and the
  commands you pass to `exec`/`build`; it runs `adb`, `git` (branch and commit of the app being run) and `ps`
- **Network**: HTTP requests to `127.0.0.1` only — the Dart VM service of apps that `devctl` started — to check they
  respond. Nothing leaves your machine
- **Reads** `android/app/build.gradle(.kts)` of the running app to find its `applicationId`
- **Writes** under `~/.anti-stuck/`: the device ledger and app logs (`state/devices/`), the last Marionette address,
  this pack's rule files (`packs/flutter/`) and a launcher `~/.anti-stuck/bin/devctl`, created at session start
- **Stops** an app or emulator only when you run `devctl stop`, or when a device has been left free for 60 min.
  When a session goes idle it releases its devices but leaves apps running

## Options

`android_package` — set it if the `applicationId` cannot be read from Gradle files.

## Requirements

macOS or Linux with `python3`, the Flutter SDK, and `adb`/Xcode tools for the devices you use. MIT licensed.
