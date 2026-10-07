#!/usr/bin/env python3
"""PostToolUse(Bash, asyncRewake) — after `devctl wait <device>`, watch the ledger and wake this session when the
device is free.

Claude Code runs this in the background; exit code 2 wakes the session (even when it is idle) and shows stderr to it.
- exit 0 at once: the command was not `devctl wait`, or the device was already free / not in use
- exit 2 "free": the device has no owner (or its owner session died) — every waiting session is woken; the first to
  take it gets it
- exit 2 "still in use": the watch deadline came first, so the session decides whether to wait again. Never waits forever
Reads only the local ledger file, every POLL_SEC.
"""
import json
import os
import re
import sys
import time

HOME = os.environ.get('ANTI_STUCK_HOME') or os.path.expanduser('~/.anti-stuck')
LEDGER = os.path.join(HOME, 'state', 'devices', 'ledger.json')
POLL_SEC = 2
WATCH_SEC = int(os.environ.get('ANTI_STUCK_WATCH_SEC', '1740'))  # hook timeout is 1800 s; wake before it
WAIT = re.compile(r'(?:^|[\s;&|(\'"])(?:\S*/)?devctl\s+wait\s+[\'"]?([^\s\'";&|]+)')


def wake(msg):
    print(f'[anti-stuck-flutter: devctl] {msg}', file=sys.stderr)
    sys.exit(2)


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, TypeError):
        return True


def device(key):
    try:
        return json.load(open(LEDGER)).get('devices', {}).get(key)
    except (OSError, ValueError):
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return
    m = WAIT.search((data.get('tool_input') or {}).get('command', ''))
    if not m:
        return
    key = m.group(1)
    resp = data.get('tool_response')
    text = resp if isinstance(resp, str) else json.dumps(resp) if resp is not None else ''
    if 'nobody is using it' in text or 'free (app still running)' in text or 'already mine' in text:
        return  # nothing to wait for; devctl already told the session to take it
    devctl = os.path.join(os.environ.get('CLAUDE_PLUGIN_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'scripts', 'devctl')
    deadline = time.time() + WATCH_SEC
    while time.time() < deadline:
        d = device(key)
        owner = (d or {}).get('owner')
        if d is None or not owner or not alive(owner.get('pid')):
            ws = ((d or {}).get('app') or {}).get('ws')
            app = f' The app is still running — Marionette address {ws}.' if ws else ''
            wake(f'{key} is free now.{app} If you will use it right away, take it now with `{devctl} run {key}` '
                 f'(or `exec`/`build`); the first session to take it gets it. If another session got there first, '
                 f'`{devctl} wait {key}` again. If you no longer need it, do nothing.')
        time.sleep(POLL_SEC)
    wake(f'{key} is still in use after {WATCH_SEC // 60} min of waiting. Check `{devctl} status`, tell the user, and either '
         f'wait again with `{devctl} wait {key}` or do something else.')


if __name__ == '__main__':
    main()
