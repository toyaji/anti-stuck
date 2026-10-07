#!/usr/bin/env python3
"""Background-task ledger ($ANTI_STUCK_HOME/state/bg-ledger.json) — a session never loses track of work it started.

- PostToolUse Bash(run_in_background) / Agent(background): record start and deadline (eta; default Bash 300 s, Agent 600 s)
- SubagentStop: mark the Agent entry whose response mentions the agent_id as finished
- PreToolUse(all tools): finished or overdue entries not yet reported -> inject "check and report now"
  (at most once per entry per 60 s)
- Stop: finished or overdue unreported entries block the stop once so the model reports them
- After reporting, the model clears entries with `anti-stuck bg done <id>` (or `done all`). Entries older than 24 h expire
"""
import fcntl
import json
import os
import re
import sys
import time

ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, 'scripts', 'anti-stuck')
HOME = os.environ.get('ANTI_STUCK_HOME') or os.path.expanduser('~/.anti-stuck')
LEDGER = os.path.join(HOME, 'state', 'bg-ledger.json')
DEFAULT_ETA = {'Bash': 300, 'Agent': 600}
NAG_INTERVAL = 60
MAX_AGE = 24 * 3600


class Ledger:
    def __enter__(self):
        os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
        self.f = open(LEDGER, 'a+')
        fcntl.flock(self.f, fcntl.LOCK_EX)
        self.f.seek(0)
        try:
            self.items = json.load(self.f)
        except ValueError:
            self.items = []
        now = time.time()
        self.items = [i for i in self.items if now - i['started'] < MAX_AGE]
        return self

    def __exit__(self, *exc):
        self.f.seek(0)
        self.f.truncate()
        json.dump(self.items, self.f, indent=1)
        self.f.close()


def emit(obj):
    print(json.dumps(obj))


def summary(tool, inp):
    if tool == 'Bash':
        return re.sub(r'\s+', ' ', inp.get('command', ''))[:120]
    return f"{inp.get('subagent_type', 'agent')}: {inp.get('description', '')}"[:120]


def eta_of(tool, inp):
    m = re.match(r'\s*#\s*eta:(\d+)', inp.get('command', '')) if tool == 'Bash' else None  # header line only
    return int(m.group(1)) if m else DEFAULT_ETA.get(tool, 300)


def post_tool_use(d):
    tool = d.get('tool_name')
    inp = d.get('tool_input') or {}
    if tool not in DEFAULT_ETA:
        return
    if tool == 'Bash' and inp.get('run_in_background') is not True:
        return
    if tool == 'Agent' and inp.get('run_in_background') is False:
        return
    resp = d.get('tool_response')
    text = resp if isinstance(resp, str) else json.dumps(resp) if resp is not None else ''
    now = time.time()
    eta = eta_of(tool, inp)
    entry_id = (d.get('tool_use_id') or f'{tool}-{int(now)}')[-12:]
    with Ledger() as led:
        led.items.append({
            'id': entry_id, 'tool': tool, 'session': d.get('session_id', ''), 'what': summary(tool, inp),
            'started': now, 'eta': eta, 'response': text[:400],
            'finished': None, 'nagged': 0, 'blocked_stop': False,
        })
    emit({'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext':
          f'[anti-stuck: background ledger] registered as {entry_id}, expected to finish by '
          f'{time.strftime("%H:%M", time.localtime(now + eta))} (eta {eta} s). Tell the user that time. When it ends, '
          f'report the result and run `{TOOL} bg done {entry_id}`.'}})


def subagent_stop(d):
    aid = d.get('agent_id') or ''
    if not aid:
        return
    with Ledger() as led:
        for i in led.items:
            if i['tool'] == 'Agent' and aid in i.get('response', '') and not i['finished']:
                i['finished'] = time.time()


def due_items(items, session):
    now = time.time()
    return [i for i in items
            if not (session and i.get('session') and i['session'] != session)
            and (i['finished'] or now > i['started'] + i['eta'])]


def describe(i):
    now = time.time()
    state = 'finished' if i['finished'] else f'overdue by {int((now - i["started"] - i["eta"]) / 60)} min'
    return f"[{i['id']}] {i['tool']} {state} · {i['what']}"


def pre_tool_use(d):
    with Ledger() as led:
        due = [i for i in due_items(led.items, d.get('session_id')) if time.time() - i['nagged'] > NAG_INTERVAL]
        for i in due:
            i['nagged'] = time.time()
    if due:
        emit({'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'additionalContext':
              '[anti-stuck: background ledger] unreported work: ' + ' / '.join(describe(i) for i in due) +
              '. Check its state now and tell the user (finished / failed / still running); clear finished ones with '
              f'`{TOOL} bg done <id>`.'}})


def stop(d):
    with Ledger() as led:
        due = [i for i in due_items(led.items, d.get('session_id')) if not i['blocked_stop']]
        for i in due:
            i['blocked_stop'] = True
    if due:
        emit({'decision': 'block', 'reason':
              '[anti-stuck: background ledger] background work was never reported: ' +
              ' / '.join(describe(i) for i in due) +
              '. Check it, tell the user in one line, clear finished entries with `{TOOL} bg done <id>`, then stop.'})


def cli(args):
    if args and args[0] == 'done' and len(args) > 1:
        with Ledger() as led:
            led.items = [] if args[1:] == ['all'] else [i for i in led.items if i['id'] not in args[1:]]
            left = len(led.items)
        print(f'{left} entries left')
    elif args and args[0] == 'list':
        with Ledger() as led:
            items = list(led.items)
        for i in items:
            print(describe(i) if (i['finished'] or time.time() > i['started'] + i['eta'])
                  else f"[{i['id']}] {i['tool']} running · {i['what']}")
        if not items:
            print('ledger is empty')
    else:
        sys.exit('usage: anti-stuck bg list | done <id>... | done all')


def main():
    if len(sys.argv) > 1:
        cli(sys.argv[1:])
        return
    try:
        d = json.load(sys.stdin)
    except ValueError:
        return
    ev = d.get('hook_event_name')
    if ev == 'PostToolUse':
        post_tool_use(d)
    elif ev == 'SubagentStop':
        subagent_stop(d)
    elif ev == 'PreToolUse':
        pre_tool_use(d)
    elif ev == 'Stop':
        stop(d)


if __name__ == '__main__':
    main()
