# Anti-Stuck

**A stuck agent is worse than a failed one.** A failed command tells you something went wrong.
A stuck one burns your afternoon while you wait for a result that already arrived — or never will.

Anti-Stuck is a Claude Code plugin that makes sure Claude never waits forever on a command, a tool,
a device or a subagent, and always tells you when long or background work ends.
Framework **packs** add rules for their own ecosystems — the first one is for Flutter.

## Why it exists

All of these happened on one ordinary day of Flutter work with Claude Code:

- A Marionette MCP `connect` hung for **10 minutes**. MCP calls are outside the Bash timeout, and the default idle limit for a stdio MCP server is 30 minutes.
- A deploy-and-poll loop finished in 3 minutes, but Claude never said so. The user found out **17 minutes later**.
- A `flutter run` in the background was killed by a timeout, and nobody noticed until a notification arrived.
- Two sessions built for the same phone at once, and both builds failed.

None of these are bugs in a single command. They are **missing limits and missing reports**, and they are everywhere.

## What the core does (`anti-stuck`)

| Problem | What the plugin does |
|---|---|
| A Bash command hangs | Every Bash call runs inside `tlimit`, which kills the whole process group at the limit (300 s default) |
| Long commands start with no idea how long they take | Commands allowed more than 300 s must start with `# eta:<seconds> <what>`; the limit becomes `min(registry, eta × 2)` |
| One network call inside a loop hangs the whole loop | Denied: `curl` without `--max-time`, `aws` without `--cli-read-timeout`, `gh … --watch`, `sleep ≥ 60`, `setsid`/`nohup`/`disown`, `while true`, and `while`/`until` without a visible bound |
| Work finishes and Claude silently moves on | After a call over 60 s, a wait loop, an MCP call over 20 s, a kill, or a subagent run, Claude is told to report on the first line of its next reply |
| Background work is forgotten | A ledger tracks every background Bash/Agent call; overdue or finished entries are pushed back to Claude on every tool call, and an unreported one blocks the stop once (the **background-ledger** skill lists and clears entries) |
| Subagents run for an hour | Elapsed time is shown on every subagent tool call; past the limit (10 min default) its tools are denied, so it reports and stops |
| Runaway processes | Whole-disk searches older than 5 min (plus pack patterns) are killed when a session stops |
| A broken hook blocks everything | Hooks run through a launcher that lets tools through if a hook script is missing, instead of blocking every call |

## Packs

| Pack | What it adds |
|---|---|
| [`anti-stuck-flutter`](plugins/anti-stuck-flutter) | `devctl` (with a **devctl** skill) — a ledger that lets sessions share real devices, emulators and heavy builds (`status`, `run`, `exec`, `build`, `wait`, `release`, `stop`); fail-fast Marionette MCP guards; Flutter build/test time limits; routing `flutter run`/`adb`/`emulator` through `devctl`; `flutter_tester` cleanup |
| *your framework here* | Xcode, Android/Gradle, Docker, Node, Rust, Python… see [CONTRIBUTING.md](CONTRIBUTING.md) |

## Install

```bash
claude plugin marketplace add toyaji/anti-stuck
claude plugin install anti-stuck@anti-stuck
claude plugin install anti-stuck-flutter@anti-stuck   # optional, Flutter pack (installs the core too)
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

and give slow-to-fail MCP servers a hard per-call limit in `.mcp.json`, for example:

```json
{ "mcpServers": { "marionette": { "type": "stdio", "command": "marionette_mcp", "timeout": 60000 } } }
```

Without these, a hung stdio MCP server is only cut after **30 minutes**.

## Daily use

Claude gets two skills that carry the exact command paths: **background-ledger** (core) and **devctl** (Flutter pack).
Long commands start with an eta line, which Claude writes itself:

```bash
# eta:400 release apk build
<path to devctl> build -- flutter build apk --release
```

Your own limits go in a project's `.claude/command-timeouts.json` or `~/.anti-stuck/command-timeouts.json`:

```json
{ "rules": [ { "pattern": "melos run e2e", "limit": 1200 } ] }
```

## 🧯 Share your stuck

**Everyone using an AI coding agent gets stuck — in different places.** This project only gets better with your cases.

- **Got stuck?** Open a [Stuck report](https://github.com/toyaji/anti-stuck/issues/new?template=stuck-report.md): what hung, for how long, why nobody noticed, and how to reproduce it. Even without a fix, a well-described case helps the next person.
- **Have a fix?** Turn it into a rule and send a pull request:
  - a general rule (a command that needs a timeout flag, a new kind of hang) → the core
  - a rule for your language or framework → a pack folder under `plugins/anti-stuck-<framework>/`
  [CONTRIBUTING.md](CONTRIBUTING.md) shows how; most packs are three JSON files.
- Collected cases live in [docs/stuck-cases.md](docs/stuck-cases.md).

## Requirements and limits

- macOS or Linux, `python3`, `perl` (both preinstalled on macOS). Windows is not supported yet
- Rules read the command text, so a word inside an unusual quoting form can still match. Rephrase the command if that happens
- If a PreToolUse hook itself exceeds its timeout, Claude Code lets the tool run (documented behavior), so hooks only make quick checks
- State and logs live in `~/.anti-stuck/` (override with `ANTI_STUCK_HOME`). The plugins never change your `PATH`; tools are called by full path from their skills. Each plugin's own README lists exactly what it runs, reads, writes and kills

## License

MIT
