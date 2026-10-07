#!/usr/bin/env python3
"""PreToolUse(Bash) — every command runs inside tlimit (process-group timeout wrapper). Nothing runs unbounded.

- Limit: the matching rule in the registries, otherwise 300 s. Registries, later ones add to earlier ones:
  plugin default, every pack's ~/.anti-stuck/packs/<pack>/command-timeouts.json,
  ~/.anti-stuck/command-timeouts.json, the project's .claude/command-timeouts.json
- Route rules from packs (~/.anti-stuck/packs/<pack>/route-rules.json): a command matching `pattern` is denied
  with `message` unless the whole command matches `unless` (e.g. "flutter run" must go through devctl)
- First line '# tlimit:N': N up to the limit is used as is. N=1500 is allowed once, only for a command that
  was already killed at its limit
- First line '# eta:N what': declared estimate. Required when the limit is above 300 s; limit = min(limit, eta x 2).
  The eta line stays in the command so report_long_calls.py can compare estimate and actual
- Calls that can hang a whole command are denied: curl without --max-time, aws without --cli-read-timeout,
  gh ... --watch, sleep >= 60, setsid/nohup/disown, endless loops and while/until loops without a visible bound
- Calling tlimit directly is denied (no bypass)
"""
import glob, hashlib, json, os, re, shlex, sys

ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.environ.get('ANTI_STUCK_HOME') or os.path.expanduser('~/.anti-stuck')
TLIMIT = os.path.join(ROOT, 'scripts', 'tlimit')
LOG = os.path.join(HOME, 'logs', 'tlimit.log')
DEFAULT, RETRY = 300, 1500
LOG_ROTATE_BYTES = 5 * 1024 * 1024


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
          "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    sys.exit(0)


def load_list(path, key):
    try:
        return json.load(open(path)).get(key, [])
    except (OSError, ValueError, AttributeError):
        return []


def pack_files(name):
    return sorted(glob.glob(os.path.join(HOME, 'packs', '*', name)))


def registries(cwd):
    paths = [os.path.join(ROOT, 'config', 'command-timeouts.json'), *pack_files('command-timeouts.json'),
             os.path.join(HOME, 'command-timeouts.json')]
    d = cwd
    while d and d != '/':
        p = os.path.join(d, '.claude', 'command-timeouts.json')
        if os.path.isfile(p):
            paths.append(p)
            break
        d = os.path.dirname(d)
    return [r for p in paths for r in load_list(p, 'rules')]


def route_rules():
    return [r for p in pack_files('route-rules.json') for r in load_list(p, 'rules')]


def rotate_log():
    try:
        if os.path.getsize(LOG) > LOG_ROTATE_BYTES:
            os.replace(LOG, LOG + '.1')
    except OSError:
        pass


def log_lines():
    for p in (LOG, LOG + '.1'):
        try:
            with open(p) as f:
                yield from f
        except OSError:
            pass


HEADER = re.compile(r'\s*#\s*(tlimit|eta):(\d+)([^\n]*)\n')


def parse_header(cmd):
    """Read leading '# tlimit:N' / '# eta:N what' comments. The tlimit line is dropped, the eta line is kept."""
    asked = eta = None
    keep = []
    rest = cmd
    while True:
        m = HEADER.match(rest)
        if not m:
            break
        if m.group(1) == 'tlimit':
            asked = int(m.group(2))
        else:
            eta = int(m.group(2))
            keep.append(m.group(0).lstrip())
        rest = rest[m.end():]
    return asked, eta, ''.join(keep) + rest


UNQUOTE = re.compile(r"'[^']*'|\"[^\"]*\"")
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\s*(\n|$)", re.S)
LOOP = re.compile(r'\b(while|until)\b[^\n]*?\bdo\b')
ENDLESS = re.compile(r'\bwhile\s+(true|:|\[\s*1\s*\]|\[\[\s*1\s*\]\])\s*[;\n]|\buntil\s+false\s*[;\n]')
BOUND = re.compile(r'\$SECONDS|\bSECONDS\b|-(lt|gt|le|ge)\b|\bseq\s+\d|\bbreak\b|\$\(\(\s*\w+\s*[-+]|\(\(\s*\w+\s*[-+<>]')


def code_only(body):
    """Strip heredoc bodies and string literals so text inside them is not mistaken for commands."""
    return UNQUOTE.sub("''", HEREDOC.sub('\n', body))


def check_per_call_limits(u):
    if re.search(r'(^|[\s;&|(])(setsid|nohup|disown)\b', u):
        deny('setsid/nohup/disown escape the tlimit process group and become orphans outside any time limit. '
             'Run long-lived work through a pack tool built for it; run everything else in the foreground.')
    if re.search(r'\bgh\s+run\s+watch\b|\bgh\b[^\n;&|]*\s--watch\b', u):
        deny('gh ... --watch waits until the run ends, however long that is. Query once (gh run view / gh pr checks), '
             'report the result, and query again in a later turn if needed.')
    for m in re.finditer(r'\bsleep\s+(\d+(?:\.\d+)?)', u):
        if float(m.group(1)) >= 60:
            deny(f'sleep {m.group(1)} is 60 s or more. Do not wait long inside one Bash call — check briefly, report, '
                 'and check again in a later turn.')
    if re.search(r'(^|[\s;&|(])curl\b', u) and not re.search(r'--max-time\b|\s-m\s*\d|--connect-timeout\b', u):
        deny('curl needs --max-time <seconds>. Without it a silent server hangs the call forever.')
    if re.search(r'(^|[\s;&|(])aws\s+(?!configure\b|--version\b|help\b)', u) and not re.search(r'--cli-read-timeout\b', u):
        deny('aws calls need --cli-read-timeout <seconds> (and preferably --cli-connect-timeout). Example: '
             'aws --cli-read-timeout 30 --cli-connect-timeout 10 ecs describe-services ...')
    if ENDLESS.search(u):
        deny('No endless loops (while true / until false). Bound the loop by SECONDS or a counter and print '
             '"limit reached" when the bound is hit.')
    if LOOP.search(u) and not BOUND.search(u):
        deny('This while/until loop has no visible bound (SECONDS comparison, -lt/-gt counter, seq, or break). '
             'Add one and print "limit reached" when it is hit.')


def check_routes(code, cmd):
    for r in route_rules():
        try:
            hit = re.search(r['pattern'], code)
            spared = r.get('unless') and re.search(r['unless'], cmd)
        except (re.error, KeyError, TypeError):
            continue
        if hit and not spared:
            deny(r.get('message') or f"An anti-stuck pack routes this command elsewhere ({r['pattern']}).")


def main():
    data = json.load(sys.stdin)
    inp = data.get('tool_input') or {}
    cmd = inp.get('command', '')
    if re.search(r'(^|[;&|(]\s*|\n\s*)(\S*/)?tlimit\s+\d', cmd):
        deny("Do not call tlimit directly. For a long command add '# eta:<seconds> <what>' (registered commands) "
             "or '# tlimit:1500' once after it was killed.")
    asked, eta, body = parse_header(cmd)
    code = code_only(body)
    check_per_call_limits(code)
    check_routes(code, cmd)
    norm = re.sub(r'\s+', ' ', re.sub(r'^\s*#\s*eta:[^\n]*\n', '', body)).strip()
    key = hashlib.sha1(norm.encode()).hexdigest()
    norm_code = re.sub(r'\s+', ' ', code).strip()

    limit = DEFAULT
    for r in registries(data.get('cwd') or os.getcwd()):
        try:
            if re.search(r['pattern'], norm_code):
                limit = max(limit, int(r['limit']))
        except (re.error, KeyError, ValueError, TypeError):
            pass

    secs = limit
    if asked is not None:
        if asked <= limit:
            secs = asked
        elif asked == RETRY:
            killed = retried = False
            for line in log_lines():
                f = line.rstrip('\n').split('\t')
                if len(f) >= 5 and f[4] == key:
                    if f[1] == 'KILLED' and int(f[2]) < RETRY:
                        killed = True
                    if int(f[2]) == RETRY:
                        retried = True
            if not killed:
                deny(f'This command has no record of being killed at its {limit} s limit. The 1500 s retry is only for '
                     'a command that was killed, and only once.')
            if retried:
                deny('This command already had its one 1500 s retry. Split it or find out why it is slow.')
            secs = RETRY
        else:
            deny(f'Allowed: {limit} s (registry), or 1500 s once after being killed. Requested {asked} s.')

    if secs > DEFAULT:
        if eta is None:
            deny(f'This is a long command ({secs} s limit). Put `# eta:<expected seconds> <what>` on the first line and '
                 'tell the user the expected time before running it. The limit becomes min(registry, eta x 2).')
        secs = min(secs, max(eta * 2, 60))

    rotate_log()
    wrapped = f"{shlex.quote(TLIMIT)} {secs} {shlex.quote(body)} {key}"
    new = dict(inp)
    new['command'] = wrapped
    new['timeout'] = min(600000, secs * 1000 + 15000)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": new}}))


try:
    main()
except SystemExit:
    raise
except Exception as e:  # a broken rule must not let the command run unbounded
    deny(f'anti-stuck timeout hook failed, command blocked: {e}')
