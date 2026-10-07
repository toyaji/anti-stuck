# Contributing

Two ways to help: **report a stuck case**, or **turn a fix into a rule**.

## Report a stuck case

Open a [Stuck report](https://github.com/toyaji/anti-stuck/issues/new?template=stuck-report.md). The most useful reports answer:

1. What was Claude waiting on? (a command, an MCP tool, a subagent, a device, a CI run…)
2. How long, and how did you find out?
3. Why did nobody notice? (no timeout, no report, a loop that never broke, a call that never returned…)
4. A command or setup that reproduces it.

## Add a rule to the core

Change `plugins/anti-stuck/` when the case is not tied to one framework — for example a CLI that needs a timeout flag
(`curl --max-time`, `aws --cli-read-timeout`) or a new kind of hang. Add a fixture to `tests/test_hooks.py` that
fails before your change and passes after it.

## Add a pack for your framework

A pack is a plugin folder `plugins/anti-stuck-<framework>/` that depends on the core and publishes rules the core reads.
Most packs need only the three JSON files.

```text
plugins/anti-stuck-<framework>/
├── .claude-plugin/plugin.json        # "dependencies": ["anti-stuck"]
├── hooks/hooks.json                  # SessionStart → scripts/install_pack.sh
├── pack/
│   ├── command-timeouts.json         # {"rules": [{"pattern": "<regex>", "limit": <seconds>}]}
│   ├── route-rules.json              # {"rules": [{"pattern": "<regex>", "unless": "<regex>", "message": "..."}]}
│   └── reap-patterns.json            # {"patterns": [{"match": "<regex>", "orphan": true, "max_age": <s>, "reason": "..."}]}
├── scripts/install_pack.sh           # copies pack/*.json to ~/.anti-stuck/packs/<framework>/ 
├── scripts/run.sh                    # copy of the core launcher, for any hook scripts of your own
├── skills/<tool>/SKILL.md            # how Claude calls your tools, by full path
├── README.md                         # 40+ words, and what the pack runs, reads, writes and kills
└── LICENSE
```

| File | The core uses it to |
|---|---|
| `command-timeouts.json` | give slow commands (builds, test suites) a longer limit; anything above 300 s still needs `# eta:` |
| `route-rules.json` | deny a command that must go through another tool, with a message saying which (`unless` matches the allowed form) |
| `reap-patterns.json` | kill runaway processes when a session stops (`orphan`: parent gone, `max_age`: older than N s) |

Rules for packs:

- **Do not add a PreToolUse hook on Bash that rewrites the command.** Only the core wraps commands; two wrappers conflict.
  Checks that only allow or deny (like the Flutter pack's Marionette guard) are fine.
- Hook scripts run through `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/<script>"` so a missing file never blocks every tool call.
- No top-level `bin/` folder (claude.ai and Cowork refuse to install plugins that have one). Put tools in `scripts/` and tell Claude about them in a skill (`skills/<name>/SKILL.md`) that names the full path `"${CLAUDE_PLUGIN_ROOT}/scripts/<tool>"` — Claude Code substitutes it. Do not change `PATH`. In hook messages, build the path from the `CLAUDE_PLUGIN_ROOT` environment variable; in pack JSON, use a placeholder that `install_pack.sh` fills in (see the Flutter pack's `{{DEVCTL}}`).
- Each plugin folder needs its own `README.md` and `LICENSE` so it can be submitted to Anthropic's directory on its own.
- Hooks must finish in a few seconds: if a PreToolUse hook times out, Claude Code runs the tool anyway.
- Add the pack to `.claude-plugin/marketplace.json` and to the Packs table in `README.md`.
- See `plugins/anti-stuck-flutter/` for a complete example.

## Test

```bash
python3 tests/test_hooks.py
claude plugin validate .
claude plugin validate plugins/<plugin>
```
