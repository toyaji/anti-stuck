# Flutter Anti-Stuck

**A stuck agent is worse than a failed one.** This Claude Code plugin makes sure that, during Flutter work,
Claude never waits forever on a command, a device, a Marionette call or a subagent — and always tells you
when long or background work ends.

Built after one day in which a Marionette `connect` hung for 10 minutes, a finished deploy went unreported
for 17 minutes, and two sessions fought over the same phone.

## What it does

| Problem | What the plugin does |
|---|---|
| A Bash command hangs (build, test, `adb`, a polling loop) | Every Bash call runs inside `tlimit`, which kills the whole process group at the limit (300 s default, Flutter defaults in `config/command-timeouts.json`) |
| Long commands start with no idea how long they take | Commands allowed more than 300 s must start with `# eta:<seconds> <what>`; the limit becomes `min(registry, eta × 2)` |
| One network call inside a loop hangs the whole loop | Denied: `curl` without `--max-time`, `aws` without `--cli-read-timeout`, `gh … --watch`, `sleep ≥ 60`, `setsid`/`nohup`/`disown`, `while true`, and `while`/`until` without a visible bound |
| Work finishes and Claude silently moves on | After a call over 60 s, a wait loop, a 20 s+ MCP call, a kill, or a subagent run, Claude is told to report on the first line of its next reply |
| Background work is forgotten | A ledger tracks every background Bash/Agent; overdue or finished entries are pushed back to Claude on every tool call, and an unreported one blocks the stop once (`fas-bg list` / `fas-bg done <id>`) |
| Marionette MCP hangs when the app is backgrounded or the previous connection is paused | The VM is checked in 3 s before each call, a paused previous connection blocks `connect`, and Android apps must be in the foreground |
| Several sessions share one phone, emulator or build machine | `devctl` keeps a shared ledger: `status`, `run`, `exec`, `build` (one at a time), `wait`, `release` (keeps the app running for the next session), `stop` |
| Runaway processes | Orphaned / 30 min+ `flutter_tester` and 5 min+ whole-disk searches are killed when a session stops |
| Subagents run for an hour | Elapsed time is shown on every subagent tool call; past the limit (10 min default) tools are denied so it reports and stops |

## Install

```bash
claude plugin marketplace add toyaji/flutter-anti-stuck
claude plugin install flutter-anti-stuck@flutter-anti-stuck
```

Then add the MCP limits that a plugin cannot set for you. In `~/.claude/settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT": "60000",
    "MCP_TOOL_TIMEOUT": "180000",
    "CLAUDE_CODE_ASYNC_AGENT_STALL_TIMEOUT_MS": "300000"
  }
}
```

and give the Marionette server a hard per-call limit in your project's `.mcp.json`:

```json
{ "mcpServers": { "marionette": { "type": "stdio", "command": "marionette_mcp", "timeout": 60000 } } }
```

Without these, a hung stdio MCP server is only cut after **30 minutes** (Claude Code's default idle limit).

## Daily use

```bash
devctl status                                  # who uses which device, app build, Marionette address
devctl run <device-id> --dart-define=STAGE=dev  # take the device and start the app (reuses it if already up)
devctl exec <device-id> -- adb -s <device-id> exec-out screencap -p > shot.png
devctl build -- flutter build apk               # one heavy build at a time across sessions
devctl release <device-id>                     # hand back; the app stays up for the next session
fas-bg list                                    # background work this plugin is tracking
```

Long command example — Claude writes this itself once the plugin is on:

```bash
# eta:400 release apk build
devctl build -- flutter build apk --release
```

Project-specific limits go in `.claude/command-timeouts.json`:

```json
{ "rules": [ { "pattern": "melos run e2e", "limit": 1200 } ] }
```

## Options

Set in `/plugin` → flutter-anti-stuck → configure, or `/config`:

| Option | Default | Meaning |
|---|---|---|
| `agent_limit_minutes` | 10 | Subagent time limit |
| `require_foreground_agents` | true | Deny background Agent calls |
| `allow_background` | false | Allow background Bash without the user asking |
| `android_package` | auto | Android `applicationId` for the foreground check |

## Requirements and limits

- macOS or Linux, `python3`, `perl` (both preinstalled on macOS). Windows is not supported
- Rules read command text, so a word inside a string can match. Rephrase the command if that happens
- If a PreToolUse hook itself exceeds its timeout, Claude Code lets the tool run (documented behavior), so hooks only make 3 s network checks
- State and logs live in `~/.flutter-anti-stuck/` (override with `FAS_HOME`)

## License

MIT
