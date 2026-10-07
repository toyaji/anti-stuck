# Plugin best practices — research (2026-10-07)

Sources: Claude Code docs (plugins components, manifest reference, publish), claude.com directory docs
(pre-submission checklist, platform support, org sync), and the official marketplace plugins
`hookify`, `ralph-loop`, `security-guidance`, `claude-security` as installed locally.

## 1. How official plugins expose a tool to Claude

| Pattern | Who uses it | Notes |
|---|---|---|
| `bin/` on PATH | No official plugin found | Docs: Claude Code appends `bin/` **after** the user's PATH, "so a plugin can't shadow `git`, `ls`, or another system command". claude.ai and Cowork refuse plugins with a top-level `bin/` |
| Script in `scripts/`, called by full path from a **command or skill** | `ralph-loop`: `commands/ralph-loop.md` runs `"${CLAUDE_PLUGIN_ROOT}/scripts/setup-ralph-loop.sh"` with `allowed-tools: Bash(${CLAUDE_PLUGIN_ROOT}/scripts/…)` | Docs: `${CLAUDE_PLUGIN_ROOT}` is substituted inline in skill, command and agent Markdown. Directory docs recommend exactly this for executables |
| Script called only by hooks | `hookify`, `security-guidance`, `claude-security` | `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/x.py"` or a launcher |

**Conclusion:** expose `devctl` and `stuck-bg` through a skill (and hook messages) that carry the full
`${CLAUDE_PLUGIN_ROOT}/scripts/...` path. No launcher in the home folder, no PATH change.
Our 0.3.0 prepends `~/.anti-stuck/bin` to PATH, which is the opposite of the documented `bin/` semantics
(append, never shadow).

## 2. Hook launchers

`security-guidance` runs every hook through `hooks/sg-python.sh <script>`: finds a working Python 3
(skips the Windows Store stub, prefers newer versions), sets `PYTHONUTF8=1`, converts Windows paths,
prints a clear error if no Python exists. Our `run.sh` follows the same pattern for a different reason
(a missing script must not exit 2 and block every tool). Combining both is the best version.

## 3. Persistent state

| Location | Who uses it | Fits us? |
|---|---|---|
| `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/<id>/`) — docs' recommended place, survives updates | — | Per plugin. The core and the Flutter pack need **one shared** folder (pack rules, ledger), and Bash commands do not receive the variable |
| Project files `.claude/<plugin>.local.md` | `hookify`, `ralph-loop` | Per-project only; our ledger must be machine-wide |
| A fixed folder under the home directory | `security-guidance` (`~/.claude/security`) | Matches our need. Keep `~/.anti-stuck/`, documented in the README |

## 4. Rules we got wrong and should fix

| Item | Finding |
|---|---|
| PATH prepend in `tlimit` | Remove (see §1) |
| `~/.anti-stuck/bin` launchers | Remove; a skill gives Claude the full path |
| Loop rule | False positive: `cmd \| while read f; do …; done` is bounded by its input but is denied. Treat `while read` / `while IFS= read` as bounded |
| Hook launcher | Add Python discovery and `PYTHONUTF8=1` from the official launcher |

## 5. Directory review points we already meet

Per-plugin README and LICENSE, no `bin/`, full `${CLAUDE_PLUGIN_ROOT}` paths in hook commands, no network
except `127.0.0.1`, readable source, behavior disclosed in README. Still held for a human reviewer (not a
rejection): hooks run Python through a launcher, which the validator cannot follow.

## 6. Applied in 0.4.0

- `tlimit` no longer touches `PATH`; `~/.anti-stuck/bin` launchers and the core's SessionStart installer are gone
- New skills: `background-ledger` (core) and `devctl` (Flutter pack) give Claude the full `${CLAUDE_PLUGIN_ROOT}/scripts/...` path
- Hook messages name the installed path (`CLAUDE_PLUGIN_ROOT` in hooks; `{{DEVCTL}}` filled in by `install_pack.sh` for pack JSON)
- `run.sh` finds a Python 3.8+ interpreter and sets `PYTHONUTF8=1`; a missing script or interpreter passes instead of blocking
- `while read` / `while IFS= read` loops count as bounded
- `# eta:` is read from the command's header line only (text inside a command body no longer counts)
