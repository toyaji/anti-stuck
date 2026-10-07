#!/usr/bin/env python3
"""PreToolUse(all tools) · SubagentStop — background work and subagents stay bounded and reported.

- Bash run_in_background is denied unless the user's last message asked for background work
  (plugin option allow_background = true turns this off)
- Agent must be called with run_in_background: false (plugin option require_foreground_agents = false turns this off)
- Inside a subagent every tool call shows elapsed time; past agent_limit_minutes every tool call is denied so the
  subagent reports what it has and stops
- SubagentStop logs the run and clears its clock
"""
import json
import os
import re
import sys
import time

HOME = os.environ.get('ANTI_STUCK_HOME') or os.path.expanduser('~/.anti-stuck')
CLOCK_DIR = os.path.join(HOME, 'state', 'agent-clock')
LOG = os.path.join(HOME, 'logs', 'subagents.log')


def option(name, default):
    v = os.environ.get(f'CLAUDE_PLUGIN_OPTION_{name.upper()}')
    return default if v in (None, '') else v


def flag(name, default):
    return str(option(name, default)).strip().lower() not in ('false', '0', 'no', 'off')


AGENT_LIMIT_SEC = int(float(option('agent_limit_minutes', 10)) * 60)
BG_REQUEST = re.compile(r'background|백그라운드', re.IGNORECASE)


def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def deny(reason):
    emit({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                 'permissionDecisionReason': reason}})


def last_user_text(path):
    if not path or not os.path.exists(path):
        return ''
    text = ''
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get('type') != 'user':
                continue
            c = (d.get('message') or {}).get('content')
            if isinstance(c, str):
                text = c
            elif isinstance(c, list):
                parts = [b.get('text', '') for b in c if isinstance(b, dict) and b.get('type') == 'text']
                if parts:
                    text = '\n'.join(parts)
    return text


def clock_path(agent_id):
    return os.path.join(CLOCK_DIR, re.sub(r'[^A-Za-z0-9_-]', '_', agent_id))


def pre_tool_use(data):
    tool = data.get('tool_name')
    inp = data.get('tool_input') or {}

    if tool == 'Bash' and inp.get('run_in_background') is True and not flag('allow_background', False):
        if not BG_REQUEST.search(last_user_text(data.get('transcript_path'))):
            deny('Background Bash is only allowed when the user explicitly asked for it in their last message. '
                 'Run it in the foreground (tlimit bounds it).')

    if tool == 'Agent' and inp.get('run_in_background') is not False and flag('require_foreground_agents', True):
        deny('Call Agent with run_in_background: false so you wait for it and report its result right away.')

    agent_id = data.get('agent_id')
    if not agent_id:
        sys.exit(0)
    os.makedirs(CLOCK_DIR, exist_ok=True)
    path = clock_path(agent_id)
    now = time.time()
    if not os.path.exists(path):
        with open(path, 'w') as f:
            f.write(str(now))
        start = now
    else:
        with open(path) as f:
            start = float(f.read().strip() or now)
    elapsed = now - start
    limit_min = AGENT_LIMIT_SEC / 60
    if elapsed > AGENT_LIMIT_SEC:
        deny(f'Subagent time limit of {limit_min:.0f} min exceeded ({elapsed / 60:.1f} min). Do not use more tools — '
             'report what you confirmed and what you could not, and finish now.')
    emit({'hookSpecificOutput': {'hookEventName': 'PreToolUse',
                                 'additionalContext': f'[time] {elapsed / 60:.1f} min elapsed / limit {limit_min:.0f} min'}})


def subagent_stop(data):
    agent_id = data.get('agent_id') or ''
    path = clock_path(agent_id) if agent_id else ''
    elapsed = ''
    if path and os.path.exists(path):
        with open(path) as f:
            elapsed = f'{(time.time() - float(f.read().strip() or time.time())) / 60:.1f}min'
        os.remove(path)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{data.get('agent_type', '')}\t{agent_id}\t"
                f"{elapsed}\t{data.get('session_id', '')}\n")
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        sys.exit(0)
    event = data.get('hook_event_name')
    if event == 'PreToolUse':
        pre_tool_use(data)
    elif event == 'SubagentStop':
        subagent_stop(data)
    sys.exit(0)


if __name__ == '__main__':
    main()
