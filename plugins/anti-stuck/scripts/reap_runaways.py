#!/usr/bin/env python3
"""Stop / SubagentStop hook — kill runaway processes that sessions leave behind. Only listed patterns are touched.

Patterns: the core's whole-disk searches, plus every pack's ~/.anti-stuck/packs/<pack>/reap-patterns.json:
  {"patterns": [{"match": "<regex on the command line>", "orphan": true, "max_age": 1800, "reason": "..."}]}
  - orphan: kill when the parent is gone (ppid 1)
  - max_age: kill when older than this many seconds
Anything a user started that matches no pattern is never touched.
"""
import glob
import json
import os
import re
import subprocess
import time

HOME = os.environ.get('ANTI_STUCK_HOME') or os.path.expanduser('~/.anti-stuck')
LOG = os.path.join(HOME, 'logs', 'reap.log')
CORE = [{'match': r'(^|/)find / |grep -r.* / ', 'max_age': 300, 'reason': 'whole-disk search older than 5 min'}]


def patterns():
    out = list(CORE)
    for p in sorted(glob.glob(os.path.join(HOME, 'packs', '*', 'reap-patterns.json'))):
        try:
            out += json.load(open(p)).get('patterns', [])
        except (OSError, ValueError, AttributeError):
            pass
    return out


def seconds(etime):
    days = 0
    if '-' in etime:
        d, etime = etime.split('-', 1)
        days = int(d)
    s = 0
    for part in etime.split(':'):
        s = s * 60 + int(part)
    return days * 86400 + s


def main():
    pats = patterns()
    try:
        ps = subprocess.run(['ps', '-eo', 'pid=,ppid=,etime=,command='], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return
    me = os.getpid()
    lines = []
    for row in ps.splitlines():
        parts = row.split(None, 3)
        if len(parts) < 4:
            continue
        pid, ppid, etime, cmd = int(parts[0]), int(parts[1]), parts[2], parts[3]
        if pid == me:
            continue
        for p in pats:
            try:
                if not re.search(p['match'], cmd):
                    continue
            except (re.error, KeyError, TypeError):
                continue
            why = None
            if p.get('orphan') and ppid == 1:
                why = p.get('reason') or 'orphaned'
            elif p.get('max_age') and seconds(etime) > int(p['max_age']):
                why = p.get('reason') or f"older than {p['max_age']} s"
            if why:
                try:
                    os.kill(pid, 15)
                    lines.append(f"{time.strftime('%F %T')} kill {pid} ({why}, {etime}) {cmd[:160]}\n")
                except OSError:
                    pass
                break
    if lines:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, 'a') as f:
            f.writelines(lines)


if __name__ == '__main__':
    main()
