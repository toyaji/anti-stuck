---
name: background-ledger
description: Inspect or clear background Bash and Agent work that anti-stuck is tracking. Use when a "[anti-stuck: background ledger]" note mentions unreported work, when you start background work and need to report its expected finish time, or when the user asks what is still running in the background.
---

# Background ledger

anti-stuck records every background Bash call (`run_in_background: true`) and every background Agent call with its
start time and deadline. Finished or overdue entries are pushed back to you before tool calls, and a session cannot
stop once while one is unreported.

The command is:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/stuck-bg"
```

| Task | Command |
|---|---|
| See what is tracked | `"${CLAUDE_PLUGIN_ROOT}/scripts/stuck-bg" list` |
| Clear an entry after you reported it | `"${CLAUDE_PLUGIN_ROOT}/scripts/stuck-bg" done <id>` |
| Clear everything after reporting all of it | `"${CLAUDE_PLUGIN_ROOT}/scripts/stuck-bg" done all` |

Rules:

1. When you start background work, tell the user the expected finish time the ledger printed. Put `# eta:<seconds> <what>`
   on the first line of a background Bash command so the deadline is right.
2. When an entry is finished or overdue, check its real state (output file, process, CI run), tell the user in one line
   whether it finished, failed, or is still running, and then clear it with `done <id>`.
3. Never clear an entry you have not reported.
