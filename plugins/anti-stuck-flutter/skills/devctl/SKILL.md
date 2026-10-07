---
name: devctl
description: Share Flutter devices, emulators and heavy builds between Claude Code sessions with devctl. Use before running a Flutter app on a phone or emulator, running integration tests, installing with adb, booting an emulator, running a release build, or connecting Marionette to a running app, and whenever anti-stuck refuses a flutter/adb/emulator command and points to devctl.
---

# devctl — the shared device and build ledger

Several Claude Code sessions on one machine can use the same phone or emulator. devctl keeps one ledger so a session
never kills another session's app, never builds over another's build, and hands devices over in order.
`flutter run`, `adb install`, `emulator -avd` and similar commands are refused unless they go through devctl.

The command is:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/devctl"
```

| Task | Command |
|---|---|
| See who uses what (do this first) | `"${CLAUDE_PLUGIN_ROOT}/scripts/devctl" status` |
| Start or reuse the app on a device | `"${CLAUDE_PLUGIN_ROOT}/scripts/devctl" run <device> [flutter run args]` |
| Run a command that needs the device | `"${CLAUDE_PLUGIN_ROOT}/scripts/devctl" exec <device> -- <command>` |
| Heavy build, one at a time across sessions | `"${CLAUDE_PLUGIN_ROOT}/scripts/devctl" build -- <command>` |
| Boot an emulator and take it | `"${CLAUDE_PLUGIN_ROOT}/scripts/devctl" emu <avd>` |
| Join the queue for a busy device | `"${CLAUDE_PLUGIN_ROOT}/scripts/devctl" wait <device> "purpose"` |
| Hand a device back (the app keeps running) | `"${CLAUDE_PLUGIN_ROOT}/scripts/devctl" release <device>` |
| Stop the app (only your own, only if nobody waits) | `"${CLAUDE_PLUGIN_ROOT}/scripts/devctl" stop <device>` |

Rules:

1. Run `status` before touching any device.
2. If another session owns the device, `wait` — do not stop its app or start a second one. When it is handed to you,
   reuse the running app through the Marionette address that `status` shows instead of rebuilding.
3. `run`, `emu`, `exec` and `build` can be slow: start them with `# eta:<seconds> <what>` on the first line and tell the
   user the expected time.
4. Release a device as soon as you stop using it. A session that goes idle releases its devices automatically, and apps
   keep running for the next session.
5. Hot reload and hot restart go through the Marionette MCP `hot_reload` / `hot_restart` tools, connected to the
   address `status` shows. `flutter run` does not read keys from a pipe.
