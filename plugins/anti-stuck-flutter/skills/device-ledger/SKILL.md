---
name: device-ledger
description: Share Flutter devices, emulators and heavy builds between Claude Code sessions with anti-stuck-flutter. Use before running a Flutter app on a phone or emulator, running integration tests, installing with adb, booting an emulator, running a release build, or connecting Marionette to a running app, and whenever anti-stuck refuses a flutter/adb/emulator command and points to anti-stuck-flutter.
---

# anti-stuck-flutter — the shared device and build ledger

Several Claude Code sessions on one machine can use the same phone or emulator. anti-stuck-flutter keeps one ledger so a session
never kills another session's app, never builds over another's build, and hands devices over in order.
`flutter run`, `adb install`, `emulator -avd` and similar commands are refused unless they go through it.

The command is:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter"
```

| Task | Command |
|---|---|
| See who uses what (do this first) | `"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter" status` |
| Reuse running app or launch already-installed app + attach (no native build — default when no native code changed) | `"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter" attach <device> [flutter attach args]` |
| Full native build + install + start (only when app is not installed or native `ios/`/`android/`/`pubspec.yaml` plugins changed) | `"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter" run <device> [flutter run args]` |
| Run a command that needs the device | `"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter" exec <device> -- <command>` |
| Heavy build, one at a time across sessions | `"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter" build -- <command>` |
| Boot an emulator and take it | `"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter" emu <avd>` |
| Wait for a busy device (you are woken when it is free) | `"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter" wait <device> "purpose"` |
| Release ownership when done (the app keeps running for 15 min so the next turn/session can reuse it in 0 s; waiters are woken immediately) | `"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter" release <device>` |
| Stop the app immediately (only your own, only if nobody waits) | `"${CLAUDE_PLUGIN_ROOT}/scripts/anti-stuck-flutter" stop <device>` |

Rules:

1. Run `status` before touching any device.
2. **Prefer `attach` over `run` whenever native code (`ios/`, `android/`, native plugins in `pubspec.yaml`) has not changed.** `attach` reuses a running app in 0 s, or launches the already-installed app on the device and runs `flutter attach` (or `--use-application-binary` on iOS) without a slow Xcode/Gradle rebuild, then you apply Dart changes via Marionette `hot_restart`. Only use `run` when the app is not installed yet or native dependencies changed.
3. If another session owns the device, `wait` — do not stop its app or start a second one. After `wait` you can keep
   working on something else or stop: a hook wakes this session the moment the device is free.
4. When woken, take the device **only if you will use it right now**. Every waiting session is woken at once and the
   first to take it gets it, so a session that grabs it "for later" blocks one that is waiting with nothing else to do.
   Being woken takes you off the waiters list, so if you lose the race, `wait` again. Reuse the running app through the Marionette address in the wake message instead
   of rebuilding.
5. `run`, `attach`, `emu`, `exec` and `build` can be slow: start them with `# eta:<seconds> <what>` on the first line and tell the
   user the expected time.
6. Release a device as soon as your work on it is done (`release <device>`). `release` keeps the running app alive for 15 minutes so the next session or turn can reuse it in 0 s without rebuilding; after 15 minutes unused with nobody waiting, it is stopped and an Android phone's screen turned off. Use `stop <device>` only when you explicitly need to kill the app immediately.
7. Hot reload and hot restart go through the Marionette MCP `hot_reload` / `hot_restart` tools, connected to the
   address `status` shows. `flutter run` does not read keys from a pipe.
