#!/usr/bin/env python3
"""Fixture tests for the anti-stuck core and the Flutter pack. No device or Claude session needed.

  python3 tests/test_hooks.py
Runs against a temporary ANTI_STUCK_HOME, so your real state is never touched.
"""
import json, os, shlex, shutil, subprocess, sys, tempfile, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(REPO, 'plugins', 'anti-stuck')
FLUTTER = os.path.join(REPO, 'plugins', 'anti-stuck-flutter')
HOME = tempfile.mkdtemp(prefix='anti-stuck-test-')
CLEAN_PATH = ':'.join(p for p in os.environ.get('PATH', '').split(':') if '.anti-stuck' not in p)
ENV = {**os.environ, 'PATH': CLEAN_PATH, 'ANTI_STUCK_HOME': HOME, 'CLAUDE_PLUGIN_ROOT': CORE}
fails = 0


def hook(root, script, payload, env=None):
    p = subprocess.run(['sh', os.path.join(root, 'scripts', 'run.sh'), os.path.join(root, 'scripts', script)], input=json.dumps(payload),
                       capture_output=True, text=True, env={**ENV, 'CLAUDE_PLUGIN_ROOT': root, **(env or {})}, timeout=20)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def check(name, ok, detail=''):
    global fails
    fails += 0 if ok else 1
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  -> {str(detail)[:200]}'))


def enforce(cmd, cwd='/tmp'):
    _, out, err = hook(CORE, 'enforce_tlimit.py', {'tool_name': 'Bash', 'cwd': cwd, 'tool_input': {'command': cmd}})
    o = json.loads(out)['hookSpecificOutput']
    return o.get('permissionDecision', 'allow'), o.get('permissionDecisionReason') or o['updatedInput']['command']


# ── launcher
rc, _, err = hook(CORE, 'no_such_script.py', {})

check('run.sh: missing script passes (exit 0), never blocks', rc == 0 and 'missing' in err, (rc, err))

# ── core rules, no packs installed
for name, cmd, want in [
    ('plain', 'ls', 'allow'),
    ('curl without max-time', 'curl https://x.io', 'deny'),
    ('curl with max-time', 'curl --max-time 3 https://x.io', 'allow'),
    ('aws without read timeout', 'aws s3 ls', 'deny'),
    ('aws with read timeout', 'aws --cli-read-timeout 5 s3 ls', 'allow'),
    ('unbounded while', 'while ! test -f x; do sleep 1; done', 'deny'),
    ('bounded while', 'SECONDS=0; while [ $SECONDS -lt 9 ]; do sleep 1; done', 'allow'),
    ('while true', 'while true; do sleep 1; done', 'deny'),
    ('sleep 61', 'sleep 61', 'deny'),
    ('gh run watch', 'gh run watch 5', 'deny'),
    ('nohup', 'nohup x &', 'deny'),
    ('heredoc body ignored', "cat > f <<EOF\ncurl later\nEOF\n", 'allow'),
    ('string ignored', 'echo "curl later"', 'allow'),
    ('while read over input is bounded', 'ls | while read f; do echo $f; done', 'allow'),
    ('while IFS= read is bounded', 'printf "a\\n" | while IFS= read -r l; do echo $l; done', 'allow'),
    ('direct tlimit', 'tlimit 5 ls', 'deny'),
    ('flutter run allowed without the pack', 'flutter run -d x', 'allow'),
]:
    got, text = enforce(cmd)
    check(f'core: {name}', got == want, f'{got}: {text}')

proj = os.path.join(HOME, 'proj')
os.makedirs(os.path.join(proj, '.claude'))
json.dump({'rules': [{'pattern': 'slow-thing', 'limit': 900}]}, open(os.path.join(proj, '.claude', 'command-timeouts.json'), 'w'))
check('core: project rule needs eta', enforce('slow-thing', proj)[0] == 'deny')
got, text = enforce('# eta:200 slow\nslow-thing', proj)
check('core: eta limit = eta x 2', got == 'allow' and ' 400 ' in text, text)

# real runs through tlimit
_, wrapped = enforce('echo hi; exit 3')
p = subprocess.run(wrapped, shell=True, capture_output=True, text=True, timeout=20, env=ENV)
check('tlimit: exit code passes through', p.returncode == 3 and 'hi' in p.stdout, (p.returncode, p.stdout))
_, wrapped = enforce('# tlimit:2\nsleep 8')
t0 = time.time()
p = subprocess.run(wrapped, shell=True, capture_output=True, text=True, timeout=20, env=ENV)
check('tlimit: killed at limit with 124', p.returncode == 124 and time.time() - t0 < 7, (p.returncode, time.time() - t0))
check('tlimit: log under ANTI_STUCK_HOME', 'KILLED\t2\t' in open(os.path.join(HOME, 'logs', 'tlimit.log')).read())

# learned limits from past runs
LOG = os.path.join(HOME, 'logs', 'tlimit.log')
def key_of(cmd, cwd='/tmp'):
    return shlex.split(enforce(cmd, cwd)[1])[3]
def secs_of(cmd, cwd='/tmp'):
    got, text = enforce(cmd, cwd)
    return got, (int(shlex.split(text)[1]) if got == 'allow' else text), shlex.split(text)[4:] if got == 'allow' else []
ETA = '# eta:9 x\n'  # keeps long registry rules from being denied; the key ignores it
def fake_run(cmd, status, el, cwd='/tmp'):
    with open(LOG, 'a') as f:
        f.write(f"2026-01-01 00:00:00\t{status}\t300\t{el}\t{key_of(ETA + cmd, cwd)}\t{cwd}\t{cmd}\n")

with open(LOG, 'ab') as f:
    f.write(b'2026-01-01 00:00:00\tDONE\t300\t1.0\tbadkey\t/tmp\techo \xed\x95\n')  # cut mid-character, as tlimit does
check('learn: undecodable log bytes never block a command', enforce('echo after-bad-bytes')[0] == 'allow')
check('learn: never-run command gets the registry limit', secs_of('echo learn-a')[1] == 300)
fake_run('echo learn-a', 'DONE', 2.0)
check('learn: one success is not enough to learn', secs_of('echo learn-a')[1] == 300)
fake_run('echo learn-a', 'DONE', 2.0)
got, secs, extra = secs_of('echo learn-a')
check('learn: two fast successes -> floor 120 s, full limit passed to tlimit', secs == 120 and extra == ['300'], (secs, extra))
fake_run('echo learn-a', 'DONE', 100.0)
check('learn: slowest of recent runs x1.5 + 30', secs_of('echo learn-a')[1] == 180)
check('learn: other directory does not share history', secs_of('echo learn-a', HOME)[1] == 300)
fake_run('echo learn-a', 'KILLED_LEARNED', 180.0)
check('learn: a kill at a learned limit turns learning off -> full limit', secs_of('echo learn-a')[1] == 300)
check('learn: a kill at a learned limit does not unlock the 1500 s retry', enforce('# tlimit:1500\necho learn-a')[0] == 'deny')
for _ in range(5):
    fake_run('echo learn-a', 'DONE', 10.0)
check('learn: kill older than the last 5 runs is forgotten', secs_of('echo learn-a')[1] == 120)
fake_run('echo learn-b', 'FAIL', 1.0)
fake_run('echo learn-b', 'DONE', 1.0)
check('learn: a failed run among the recent ones teaches nothing', secs_of('echo learn-b')[1] == 300)
fake_run('echo learn-c', 'DONE', 900.0)
fake_run('echo learn-c', 'DONE', 900.0)
check('learn: never above the registry limit', secs_of('echo learn-c')[1] == 300)
check('learn: explicit # tlimit:N still wins', secs_of('# tlimit:250\necho learn-a')[1] == 250)
fake_run('slow-thing', 'DONE', 40.0, proj)
fake_run('slow-thing', 'DONE', 40.0, proj)
got, secs, _ = secs_of('slow-thing', proj)
check('learn: learned limit under 300 s needs no eta even for a long registry rule', got == 'allow' and secs == 120, (got, secs))
json.dump({'rules': [{'pattern': 'slow-thing', 'limit': 900}, {'pattern': 'device-launch', 'limit': 900, 'learn': False}]},
          open(os.path.join(proj, '.claude', 'command-timeouts.json'), 'w'))
fake_run('device-launch', 'DONE', 1.0, proj)
fake_run('device-launch', 'DONE', 1.0, proj)
got, text = enforce('# eta:400 launch\ndevice-launch', proj)
check('learn: a "learn": false registry rule is never learned', got == 'allow' and ' 800 ' in text, text)
p = subprocess.run([os.path.join(CORE, 'scripts', 'tlimit'), '1', 'sleep 5', 'k-learned', '300'], capture_output=True, text=True, timeout=20, env=ENV)
check('tlimit: kill at a learned limit says re-run as is with the full limit', p.returncode == 124 and 'full 300s' in p.stderr, p.stderr)
check('tlimit: kill at a learned limit logged as KILLED_LEARNED', '\tKILLED_LEARNED\t1\t' in open(LOG, errors='replace').read())
_, wrapped = enforce('echo hi; exit 3')
subprocess.run(wrapped, shell=True, capture_output=True, text=True, timeout=20, env=ENV)
check('tlimit: non-zero exit logged as FAIL', '\tFAIL\t' in open(LOG, errors='replace').read())

# ── Flutter pack installs its rules, core picks them up
p = subprocess.run(['sh', os.path.join(FLUTTER, 'scripts', 'install_pack.sh')], env=ENV, timeout=10)
installed = sorted(os.listdir(os.path.join(HOME, 'packs', 'flutter')))
check('pack: install_pack.sh publishes 3 rule files', installed == ['command-timeouts.json', 'reap-patterns.json', 'route-rules.json'], installed)
got, text = enforce('# eta:5 x\nflutter run -d x')
check('pack route: deny message names the installed tool path', os.path.join(FLUTTER, 'scripts', 'anti-stuck-flutter') in text, text)
_, wrapped = enforce(f'{os.path.join(FLUTTER, "scripts", "anti-stuck-flutter")} status; echo PATH=$PATH')
p = subprocess.run(wrapped, shell=True, capture_output=True, text=True, timeout=20, env=ENV)
check('tools: anti-stuck-flutter runs by full path; tlimit leaves PATH untouched', p.returncode == 0 and 'no devices' in p.stdout and p.stdout.split('PATH=')[-1].strip() == CLEAN_PATH, p.stdout + p.stderr)
rc, _, err = hook(CORE, 'no_such_script.py', {})
got, text = enforce('# eta:5 x\nflutter run -d x')
check('pack route: flutter run -> anti-stuck-flutter', got == 'deny' and 'anti-stuck-flutter' in text, text)
got, _ = enforce('adb -s x install a.apk')
check('pack route: adb install -> devctl', got == 'deny')
got, text = enforce('# eta:200 build\ndevctl build -- flutter build apk')
check('pack route: devctl form allowed, pack time limit applies', got == 'allow' and ' 400 ' in text, text)
got, text = enforce('# eta:200 build\nanti-stuck-flutter build -- flutter build apk')
check('pack route: anti-stuck-flutter form allowed with the pack limit', got == 'allow' and ' 400 ' in text, text)
fake_run('anti-stuck-flutter run phone1', 'DONE', 0.5)
fake_run('anti-stuck-flutter run phone1', 'DONE', 0.5)
got, text = enforce('# eta:400 build and launch\nanti-stuck-flutter run phone1')
check('pack: anti-stuck-flutter run never learns a short limit from quick reuses', got == 'allow' and ' 800 ' in text, text)
check('pack time limit: flutter build needs eta', 'eta' in enforce('devctl build -- flutter build apk')[1])

# ── report_long_calls
def report(payload):
    _, out, _ = hook(CORE, 'report_long_calls.py', {'hook_event_name': 'PostToolUse', **payload})
    return json.loads(out)['hookSpecificOutput']['additionalContext'] if out else ''

check('report: short call silent', report({'tool_name': 'Bash', 'tool_input': {'command': 'ls'}, 'tool_response': 'x', 'duration_ms': 500}) == '')
check('report: "[tlimit]" text in normal output is not a kill', report({'tool_name': 'Bash', 'tool_input': {'command': 'grep tlimit x'}, 'tool_response': 'see [tlimit] here', 'duration_ms': 500}) == '')
check('report: 65 s call', '65 s' in report({'tool_name': 'Bash', 'tool_input': {'command': 'ls'}, 'tool_response': 'x', 'duration_ms': 65000}))
loop_wrapped = enforce('SECONDS=0; while [ $SECONDS -lt 9 ]; do sleep 1; done')[1]
check('report: loop inside tlimit wrapper', 'wait loop' in report({'tool_name': 'Bash', 'tool_input': {'command': loop_wrapped}, 'tool_response': 'x', 'duration_ms': 9000}))
check('report: MCP 25 s', 'MCP' in report({'tool_name': 'mcp__marionette__connect', 'tool_input': {}, 'tool_response': 'x', 'duration_ms': 25000}))
check('report: eta inside the body is not the header', 'eta was' not in report({'tool_name': 'Bash', 'tool_input': {'command': 'echo "# eta:5 x"; true'}, 'tool_response': 'x', 'duration_ms': 30000}))
check('report: agent end', 'subagent' in report({'tool_name': 'Agent', 'tool_input': {}, 'tool_response': 'x', 'duration_ms': 90000}))

# ── background ledger
def bg(payload):
    _, out, _ = hook(CORE, 'bg_ledger.py', payload)
    return json.loads(out) if out else None

r = bg({'hook_event_name': 'PostToolUse', 'tool_name': 'Bash', 'session_id': 'S1', 'tool_use_id': 'toolu_000000BGTEST1',
        'tool_input': {'command': '# eta:1 x\nsleep 1', 'run_in_background': True}, 'tool_response': 'started'})
check('ledger: background bash registered', r and 'BGTEST1' in r['hookSpecificOutput']['additionalContext'], r)
check('ledger: message names the full anti-stuck path', r and os.path.join(CORE, 'scripts', 'anti-stuck') + ' bg done' in r['hookSpecificOutput']['additionalContext'], r)
check('ledger: foreground bash ignored', bg({'hook_event_name': 'PostToolUse', 'tool_name': 'Bash', 'session_id': 'S1', 'tool_input': {'command': 'ls'}, 'tool_response': 'x'}) is None)
time.sleep(1.5)
r = bg({'hook_event_name': 'PreToolUse', 'tool_name': 'Read', 'session_id': 'S1', 'tool_input': {}})
check('ledger: overdue pushed on next tool call', r and 'overdue' in r['hookSpecificOutput']['additionalContext'], r)
check('ledger: not repeated within 60 s', bg({'hook_event_name': 'PreToolUse', 'tool_name': 'Read', 'session_id': 'S1', 'tool_input': {}}) is None)
check('ledger: other session not told', bg({'hook_event_name': 'PreToolUse', 'tool_name': 'Read', 'session_id': 'S2', 'tool_input': {}}) is None)
r = bg({'hook_event_name': 'Stop', 'session_id': 'S1'})
check('ledger: stop blocked once', r and r.get('decision') == 'block', r)
check('ledger: second stop passes', bg({'hook_event_name': 'Stop', 'session_id': 'S1'}) is None)
p = subprocess.run([os.path.join(CORE, 'scripts', 'anti-stuck'), 'bg', 'done', 'all'], capture_output=True, text=True, timeout=10, env=ENV)
check('ledger: anti-stuck bg done all', '0 entries left' in p.stdout, p.stdout + p.stderr)

# ── agents
def guard(payload, env=None):
    _, out, _ = hook(CORE, 'guard_agents.py', {'hook_event_name': 'PreToolUse', **payload}, env)
    return json.loads(out)['hookSpecificOutput'] if out else {}

check('agents: background agent denied', guard({'tool_name': 'Agent', 'tool_input': {}}).get('permissionDecision') == 'deny')
check('agents: option turns it off', guard({'tool_name': 'Agent', 'tool_input': {}}, {'CLAUDE_PLUGIN_OPTION_REQUIRE_FOREGROUND_AGENTS': 'false'}).get('permissionDecision') != 'deny')
check('bash bg: denied without request', guard({'tool_name': 'Bash', 'tool_input': {'command': 'ls', 'run_in_background': True}}).get('permissionDecision') == 'deny')
check('bash bg: option allows', guard({'tool_name': 'Bash', 'tool_input': {'command': 'ls', 'run_in_background': True}}, {'CLAUDE_PLUGIN_OPTION_ALLOW_BACKGROUND': 'true'}).get('permissionDecision') != 'deny')
fast = {'CLAUDE_PLUGIN_OPTION_AGENT_LIMIT_MINUTES': '0.0005'}
guard({'tool_name': 'Read', 'tool_input': {}, 'agent_id': 'agTEST'}, fast)
time.sleep(0.2)
check('agents: over limit denied', guard({'tool_name': 'Read', 'tool_input': {}, 'agent_id': 'agTEST'}, fast).get('permissionDecision') == 'deny')
hook(CORE, 'guard_agents.py', {'hook_event_name': 'SubagentStop', 'agent_id': 'agTEST'})

# ── reaper picks up pack patterns (a real orphan-free old process is hard to fake; check the pattern list)
sys.path.insert(0, os.path.join(CORE, 'scripts'))
os.environ['ANTI_STUCK_HOME'] = HOME
import importlib
reap = importlib.import_module('reap_runaways')
check('reap: core + pack patterns', any('flutter_tester' in p['match'] for p in reap.patterns()) and len(reap.patterns()) >= 2)
check('reap: etime parsing', reap.seconds('1-02:03:04') == 93784 and reap.seconds('05:06') == 306)

# ── Marionette guard (VM checks need a live app; state handling and package detection do not)
st = os.path.join(HOME, 'state', 'marionette_last_uri')
os.makedirs(os.path.dirname(st), exist_ok=True)
open(st, 'w').write('ws://127.0.0.1:1/dead=/ws')
rc, _, err = hook(FLUTTER, 'guard_marionette.py', {'tool_name': 'mcp__marionette__tap', 'tool_input': {}})
check('marionette: dead VM blocks the call (exit 2)', rc == 2 and 'did not answer' in err, err)
rc, _, _ = hook(FLUTTER, 'guard_marionette.py', {'tool_name': 'mcp__marionette__disconnect', 'tool_input': {}})
check('marionette: disconnect forgets the connection', rc == 0 and not os.path.exists(st))
rc, _, _ = hook(FLUTTER, 'guard_marionette.py', {'tool_name': 'mcp__plugin_x_marionette__tap', 'tool_input': {}})
check('marionette: plugin-scoped tool name, no connection -> pass', rc == 0)
sys.path.insert(0, os.path.join(FLUTTER, 'scripts'))
gm = importlib.import_module('guard_marionette')
app = os.path.join(HOME, 'app', 'android', 'app')
os.makedirs(app)
open(os.path.join(app, 'build.gradle.kts'), 'w').write('android {\n defaultConfig {\n  applicationId = "com.example.app"\n }\n}\n')
check('marionette: applicationId from build.gradle.kts', gm.android_package({'cwd': os.path.join(HOME, 'app')}) == 'com.example.app')

# ── devctl ledger round trip (no device needed)
dev = os.path.join(FLUTTER, 'scripts', 'anti-stuck-flutter')
out = subprocess.run([dev, 'status'], capture_output=True, text=True, timeout=15, env=ENV).stdout
check('devctl: empty status', 'no devices' in out, out)
p = subprocess.run([dev, 'build', '--', 'true'], capture_output=True, text=True, timeout=15, env=ENV)
check('devctl: build runs and auto-releases', p.returncode == 0 and 'released' in p.stdout, p.stdout + p.stderr)

# ── devctl: release frees the device; every waiter is woken; first to take it wins
fake = [subprocess.Popen(['sleep', '60']) for _ in range(3)]  # stand-ins for three Claude sessions
A, B, C = (str(f.pid) for f in fake)
def as_session(pid, *args):
    return subprocess.run([dev, *args], capture_output=True, text=True, timeout=15, env={**ENV, 'ANTI_STUCK_SESSION_PID': pid})
def ledger_dev(key):
    return json.load(open(os.path.join(HOME, 'state', 'devices', 'ledger.json')))['devices'].get(key)
as_session(A, 'exec', 'phone1', '--', 'true')
check('devctl: A owns phone1', ledger_dev('phone1')['owner']['pid'] == int(A))
p = as_session(B, 'exec', 'phone1', '--', 'true')
check('devctl: B is refused while A owns it', p.returncode != 0 and 'wait' in (p.stdout + p.stderr))
p = as_session(B, 'wait', 'phone1', 'busy elsewhere'); as_session(C, 'wait', 'phone1', 'blocked')
check('devctl: B and C are waiting', len(ledger_dev('phone1')['waiters']) == 2, p.stdout)

watch = os.path.join(FLUTTER, 'scripts', 'wait_watch.py')
WAIT_PAYLOAD = json.dumps({'tool_name': 'Bash', 'tool_input': {'command': f"{dev} wait phone1 'x'"}, 'tool_response': 'waiting'})
def start_watch(extra=None):
    w = subprocess.Popen(['sh', os.path.join(FLUTTER, 'scripts', 'run.sh'), watch], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         env={**ENV, 'CLAUDE_PLUGIN_ROOT': FLUTTER, **(extra or {})})
    w.stdin.write(WAIT_PAYLOAD)
    w.stdin.close()
    return w
def finish(w, timeout):
    try:
        w.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        w.kill(); w.wait()
    return w.returncode, w.stderr.read()
wB, wC = start_watch(), start_watch()
time.sleep(3)
check('watch: still waiting while A owns it', wB.poll() is None and wC.poll() is None)
as_session(A, 'release', 'phone1')
rB, eB = finish(wB, 10); rC, eC = finish(wC, 10)
check('watch: both waiters woken with exit 2 on release', rB == 2 and rC == 2, (rB, rC))
check('watch: wake message says free and names the tool path', all('phone1 is free' in e and dev in e for e in (eB, eC)), eB[:200])
p = as_session(C, 'exec', 'phone1', '--', 'true')
check('devctl: first to take it (C) gets it', p.returncode == 0 and ledger_dev('phone1')['owner']['pid'] == int(C), p.stdout + p.stderr)
p = as_session(B, 'exec', 'phone1', '--', 'true')
check('devctl: the later one (B) is refused and told to wait', p.returncode != 0 and 'wait' in (p.stdout + p.stderr))
check('devctl: B stays on the waiters list', [w['pid'] for w in ledger_dev('phone1')['waiters']] == [int(B)])
r, e = finish(start_watch({'ANTI_STUCK_WATCH_SEC': '3'}), 15)
check('watch: gives up and wakes after its deadline (never waits forever)', r == 2 and 'still in use' in e, e[:200])
fake[2].kill(); fake[2].wait()
r, e = finish(start_watch(), 10)
check('watch: owner session died -> device counts as free', r == 2 and 'is free' in e, e[:200])
rc, _, _ = hook(FLUTTER, 'wait_watch.py', {'tool_name': 'Bash', 'tool_input': {'command': 'ls'}, 'tool_response': 'x'})
check('watch: other commands exit 0 at once', rc == 0)
rc, _, _ = hook(FLUTTER, 'wait_watch.py', {'tool_name': 'Bash', 'tool_input': {'command': f'{dev} wait phone9'}, 'tool_response': 'phone9: nobody is using it. Use it directly.'})
check('watch: nothing to wait for -> exit 0', rc == 0)
for f in fake:
    f.kill()

# ── old names keep working for one release
p = subprocess.run([os.path.join(CORE, 'scripts', 'stuck-bg'), 'list'], capture_output=True, text=True, timeout=10, env=ENV)
check('compat: stuck-bg forwards to anti-stuck bg', p.returncode == 0 and 'ledger is empty' in p.stdout, p.stdout + p.stderr)
p = subprocess.run([os.path.join(FLUTTER, 'scripts', 'devctl'), 'status'], capture_output=True, text=True, timeout=10, env=ENV)
check('compat: devctl forwards to anti-stuck-flutter', p.returncode == 0 and ('no devices' in p.stdout or 'phone1' in p.stdout), p.stdout + p.stderr)
rc, _, _ = hook(FLUTTER, 'wait_watch.py', {'tool_name': 'Bash', 'tool_input': {'command': 'devctl wait phone9'}, 'tool_response': 'phone9: nobody is using it.'})
check('compat: watcher still recognizes `devctl wait`', rc == 0)
rc, _, _ = hook(FLUTTER, 'wait_watch.py', {'tool_name': 'Bash', 'tool_input': {'command': "python3 - <<'E'\nprint('anti-stuck-flutter wait phone1')\nE\n"}, 'tool_response': 'x'})
check('watch: a wait inside a heredoc is not a real wait', rc == 0)
_, wrapped_wait = enforce(f"{dev} wait phone1 'x'")
check('watch: recognizes a wait inside the tlimit wrapper', bool(importlib.import_module('wait_watch').WAIT.search(importlib.import_module('wait_watch').command_text(wrapped_wait))))
p = subprocess.run([os.path.join(CORE, 'scripts', 'anti-stuck')], capture_output=True, text=True, timeout=10, env=ENV)
check('anti-stuck without a subcommand prints usage', p.returncode == 2 and 'bg list' in p.stdout, p.stdout)

shutil.rmtree(HOME, ignore_errors=True)
print(f'\n{"ALL PASS" if fails == 0 else f"{fails} FAILED"}')
sys.exit(1 if fails else 0)
