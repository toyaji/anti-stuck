# Anti-Stuck (core)

Keeps Claude Code from waiting forever. Every Bash call gets a hard time limit, long commands must declare how long
they will take, calls that can hang a whole command are refused, and Claude is told to report as soon as long,
looping or background work ends. Subagents get a time budget. Framework packs such as `anti-stuck-flutter` add
their own rules on top. Full documentation, packs and how to contribute: <https://github.com/toyaji/anti-stuck>.

## What it does

- Wraps every Bash command in `scripts/tlimit`, which runs it in its own process group and kills the group at the
  limit (300 s by default; longer limits come from registries and need a `# eta:<seconds>` first line)
- Learns each repeated command's limit from its own past runs in the same directory: the slowest of the last 5
  successful runs x 1.5 + 30 s (at least 60 s, never above the registry limit). A kill or failure among them
  gives the next run its full limit again
- Refuses `curl` without `--max-time`, `aws` without `--cli-read-timeout`, `gh … --watch`, `sleep` of 60 s or more,
  `setsid`/`nohup`/`disown`, endless loops and `while`/`until` loops without a visible bound
- After a call over 60 s, a wait loop, an MCP call over 20 s, a killed command or a subagent run, adds a note asking
  Claude to report the result on the first line of its next reply
- Tracks background Bash and Agent calls in a ledger and reminds Claude about overdue or finished ones; an unreported
  one blocks the stop once
- Denies background subagents and, unless you asked for it, background Bash (both configurable)
- Times subagents and denies their tool calls past the limit (10 min by default) so they report and stop

## What it runs, reads and changes on your machine

- **Runs** `python3`, `perl` and `sh` scripts from this plugin folder as hooks. No network access, no package installs
- **Reads** the session transcript file that Claude Code passes to hooks, only to see whether your last message asked
  for background work; `ps` output to find runaway processes; the timeout registries described below
- **Writes** only under `~/.anti-stuck/` (override with `ANTI_STUCK_HOME`): logs, a background-task ledger, subagent
  clocks. It never changes `PATH` or anything outside that folder
- **Kills** only processes matching listed patterns when a session stops: whole-disk `find /` or `grep -r … /` older
  than 5 min, plus patterns that installed packs publish under `~/.anti-stuck/packs/`
- **Reads rules** from `~/.anti-stuck/packs/*/`, `~/.anti-stuck/command-timeouts.json` and a project's
  `.claude/command-timeouts.json`

## Options

`agent_limit_minutes` (10), `require_foreground_agents` (true), `allow_background` (false).

## Commands

The **background-ledger** skill gives Claude the full path of `scripts/anti-stuck`: `anti-stuck bg list` shows tracked background work,
`anti-stuck bg done <id>` clears an entry after it is reported.

## Recommended settings it cannot set for you

In `~/.claude/settings.json` → `env`: `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT=60000`, `MCP_TOOL_TIMEOUT=180000`,
`CLAUDE_CODE_ASYNC_AGENT_STALL_TIMEOUT_MS=300000`. Without them a hung stdio MCP server is cut only after 30 minutes.

## Requirements

macOS or Linux with `python3` and `perl`. MIT licensed.
