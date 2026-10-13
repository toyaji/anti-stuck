#!/usr/bin/env python3
"""PostToolUse(all tools) — a slow or killed call must be reported on the first line of the next reply.

Being stuck is worse than failing. Separately from the hard limits, this stops the model from finishing a long
wait and silently moving on. Context is injected when any of these hold:
- duration_ms >= 60 s (MCP tools: 20 s; Agent: always)
- Bash: killed by tlimit (exit 124 / '[tlimit]'), or a wait loop (while/until, for ... sleep)
- a '# eta:N' line is present -> estimate vs actual is included
"""
import json
import re
import shlex
import sys

LONG_MS = 60_000
MCP_LONG_MS = 20_000
LOOP = re.compile(r'\b(while|until)\b[^\n]*?\bdo\b|\bfor\b[^\n]*?\bdo\b[^\n]*\bsleep\b')


def unwrap_tlimit(cmd):
    """Return the body of `tlimit <secs> '<body>' <key>` as rewritten by enforce_tlimit."""
    first = cmd.split('\n', 1)[0]
    if '/tlimit' not in first:
        return cmd
    try:
        parts = shlex.split(cmd)
        return parts[2] if len(parts) >= 3 else cmd
    except ValueError:
        return cmd


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    tool = data.get('tool_name') or ''
    inp = data.get('tool_input') or {}
    dur = data.get('duration_ms')
    secs = (dur or 0) / 1000
    resp = data.get('tool_response')
    text = resp if isinstance(resp, str) else json.dumps(resp) if resp is not None else ''

    reasons = []
    if tool == 'Bash':
        cmd = unwrap_tlimit(inp.get('command', ''))
        m = re.match(r'\s*(?:#\s*tlimit:\d+[^\n]*\n\s*)?#\s*eta:(\d+)', cmd)  # header line only
        eta = int(m.group(1)) if m else None
        if '[tlimit] killed at' in text or re.search(r'exit code 124|exited with code 124', text):
            reasons.append('it was killed at its time limit — say why')
        if LOOP.search(re.sub(r"'[^']*'|\"[^\"]*\"", "''", cmd)):
            reasons.append('a wait loop finished — say whether its exit condition was met or it hit its bound')
        if dur is not None and dur >= LONG_MS:
            reasons.append(f'it took {secs:.0f} s' + (f' (eta {eta} s)' if eta else ' (no eta declared)'))
        elif eta and dur is not None and secs > eta * 1.5:
            reasons.append(f'eta was {eta} s but it took {secs:.0f} s')
    elif tool.startswith('mcp__'):
        if dur is not None and dur >= MCP_LONG_MS:
            reasons.append(f'the MCP tool took {secs:.0f} s — a healthy call usually takes a few seconds')
    elif tool == 'Agent':
        reasons.append(f'a subagent finished ({secs / 60:.1f} min)')
    elif dur is not None and dur >= LONG_MS:
        reasons.append(f'it took {secs:.0f} s')

    if not reasons:
        return
    msg = (f'[anti-stuck: report now] {tool}: ' + '; '.join(reasons) +
           '. Before any other tool call, tell the user in one line what this produced and how long it took.')
    print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': msg}}))


if __name__ == '__main__':
    main()
