# Stuck cases

Real cases where Claude Code waited far longer than it should have. Add yours with a
[Stuck report](https://github.com/toyaji/anti-stuck/issues/new?template=stuck-report.md) or a pull request to this file.

| # | Waiting on | How long | Why nobody noticed | Fix in anti-stuck |
|---|---|---|---|---|
| 1 | Marionette MCP `connect` to an Android app while the previously connected iPhone app was logging nothing | 9 min+, then interrupted | MCP calls are outside the Bash timeout; a stdio MCP server's default idle limit is 30 min. Right after the interrupt the Android app's VM answered `getVersion` normally. Which step of `connect` waited was not reproduced | MCP idle limit 60 s + `.mcp.json` `timeout`; Flutter pack checks the VM before each call and blocks `connect` when the previously connected app is still running but silent |
| 2 | Marionette `connect` to an iPhone app whose log had gone silent | 1 m 43 s | It completed 2 s before the app logged its resume handler; nothing cut the wait short | Same as #1 |
| 3 | A deploy, then a `while` loop polling `aws ecs describe-services` | Done after 3 min, reported 17 min later | The loop ended, but nothing told Claude to report; `aws` calls inside had no read timeout | Forced report after loops and 60 s+ calls; `aws` without `--cli-read-timeout` is denied |
| 4 | A background `flutter run` killed by a time limit | Unnoticed until a notification | Background work had no deadline anyone was watching | Background ledger with eta; overdue work is pushed back on every tool call |
| 5 | Two sessions building for the same phone at once | Both failed | Nothing told sessions about each other | Flutter pack `devctl` ledger: one owner per device, one heavy build at a time; waiting sessions are woken the moment a device is free |
| 6 | Subagents running 15–52 min | Until the user asked | Agent calls have no wall-clock limit | Subagent time budget; foreground-only agents by default |
| 7 | A hook script was moved while installed | Every tool call in every session blocked | `python3 <missing file>` exits 2, which Claude Code reads as "block" | Hooks run through a launcher that lets tools through when a script is missing |
