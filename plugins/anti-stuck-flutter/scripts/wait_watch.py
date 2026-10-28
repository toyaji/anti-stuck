#!/usr/bin/env python3
"""PostToolUse(Bash, asyncRewake) — while this session is on a device's waiters list, watch the ledger and wake it when
the device is free.

The trigger is the ledger, not the command text, so a wait run through a variable, an alias or a script is watched too,
and so is every device the session waits for. One watcher per session; later Bash calls exit at once while it runs.
Claude Code runs this in the background; exit code 2 wakes the session (even when it is idle) and shows stderr to it.
- exit 0 at once: this session waits for nothing, or another watcher of this session is already running
- exit 2 "free": a waited device has no owner (or its owner session died). Being woken takes the session off that
  device's waiters, so it is told once; the first session to take it gets it, the others `wait` again
- exit 2 "still in use": the watch deadline came first, so the session decides whether to wait again. Never waits forever
Reads only the local ledger file, every POLL_SEC.
"""
import fcntl
import importlib.util
import json
import os
import sys
import time
from importlib.machinery import SourceFileLoader

HOME = os.environ.get('ANTI_STUCK_HOME') or os.path.expanduser('~/.anti-stuck')
STATE = os.path.join(HOME, 'state', 'devices')
LEDGER = os.path.join(STATE, 'ledger.json')
POLL_SEC = 2
WATCH_SEC = int(os.environ.get('ANTI_STUCK_WATCH_SEC', '1740'))  # hook timeout is 1800 s; wake before it
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'anti-stuck-flutter')


def load_tool():
    loader = SourceFileLoader('anti_stuck_flutter', TOOL)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def wake(msg):
    print(f'[anti-stuck-flutter] {msg}', file=sys.stderr)
    sys.exit(2)


def read_devices():
    try:
        return json.load(open(LEDGER)).get('devices', {})
    except (OSError, ValueError):
        return {}


def waited_by(devices, pid):
    return [k for k, d in devices.items() if any(w['pid'] == pid for w in d.get('waiters', []))]


def main():
    try:
        json.load(sys.stdin)
    except ValueError:
        return
    if not any(d.get('waiters') for d in read_devices().values()):
        return  # nobody waits for anything: skip finding this session
    asf = load_tool()
    me = asf.session()
    if not waited_by(read_devices(), me['pid']):
        return
    os.makedirs(STATE, exist_ok=True)
    lock = open(os.path.join(STATE, f"watch-{me['pid']}.lock"), 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return  # this session's watcher is already running
    deadline = time.time() + WATCH_SEC
    while time.time() < deadline:
        devices = read_devices()
        keys = waited_by(devices, me['pid'])
        if not keys:
            return  # took the device or left the list some other way
        free = [k for k in keys if not devices[k].get('owner') or not asf.alive(devices[k]['owner'].get('pid'))]
        if free:
            with asf.Ledger() as led:
                for k in free:
                    if k in led.devices:
                        led.devices[k]['waiters'] = [w for w in led.devices[k]['waiters'] if w['pid'] != me['pid']]
            parts = []
            for k in free:
                ws = (devices[k].get('app') or {}).get('ws')
                parts.append(f'{k} is free now.' + (f' The app is still running — Marionette address {ws}.' if ws else ''))
            first = free[0]
            wake(' '.join(parts) + f' If you will use it right away, take it now with `{TOOL} run {first}` '
                 f'(or `exec`/`build`); the first session to take it gets it. You are off its waiters list now: if another '
                 f'session got there first, `{TOOL} wait {first}` again. If you no longer need it, do nothing.')
        time.sleep(POLL_SEC)
    keys = ', '.join(waited_by(read_devices(), me['pid']))
    wake(f'{keys} still in use after {WATCH_SEC // 60} min of waiting. You are still on the waiters list. Check '
         f'`{TOOL} status`, tell the user, and either keep waiting (the next Bash call restarts this watch) or do '
         f'something else.')


if __name__ == '__main__':
    main()
