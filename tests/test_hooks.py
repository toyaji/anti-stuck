#!/usr/bin/env python3
"""Fixture tests for the anti-stuck core and the Flutter pack. No device or Claude session needed.

  python3 tests/test_hooks.py
Runs against a temporary ANTI_STUCK_HOME, so your real state is never touched.
"""
import json, os, shutil, subprocess, sys, tempfile, time

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

# ── Flutter pack installs its rules, core picks them up
p = subprocess.run(['sh', os.path.join(FLUTTER, 'scripts', 'install_pack.sh')], env=ENV, timeout=10)
installed = sorted(os.listdir(os.path.join(HOME, 'packs', 'flutter')))
check('pack: install_pack.sh publishes 3 rule files', installed == ['command-timeouts.json', 'reap-patterns.json', 'route-rules.json'], installed)
got, text = enforce('# eta:5 x\nflutter run -d x')
check('pack route: deny message names the installed devctl path', os.path.join(FLUTTER, 'scripts', 'devctl') in text, text)
_, wrapped = enforce(f'{os.path.join(FLUTTER, "scripts", "devctl")} status; echo PATH=$PATH')
p = subprocess.run(wrapped, shell=True, capture_output=True, text=True, timeout=20, env=ENV)
check('tools: devctl runs by full path; tlimit leaves PATH untouched', p.returncode == 0 and 'no devices' in p.stdout and p.stdout.split('PATH=')[-1].strip() == CLEAN_PATH, p.stdout + p.stderr)
rc, _, err = hook(CORE, 'no_such_script.py', {})
got, text = enforce('# eta:5 x\nflutter run -d x')
check('pack route: flutter run -> devctl', got == 'deny' and 'devctl' in text, text)
got, _ = enforce('adb -s x install a.apk')
check('pack route: adb install -> devctl', got == 'deny')
got, text = enforce('# eta:200 build\ndevctl build -- flutter build apk')
check('pack route: devctl form allowed, pack time limit applies', got == 'allow' and ' 400 ' in text, text)
check('pack time limit: flutter build needs eta', 'eta' in enforce('devctl build -- flutter build apk')[1])

# ── report_long_calls
def report(payload):
    _, out, _ = hook(CORE, 'report_long_calls.py', {'hook_event_name': 'PostToolUse', **payload})
    return json.loads(out)['hookSpecificOutput']['additionalContext'] if out else ''

check('report: short call silent', report({'tool_name': 'Bash', 'tool_input': {'command': 'ls'}, 'tool_response': 'x', 'duration_ms': 500}) == '')
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
check('ledger: message names the full stuck-bg path', r and os.path.join(CORE, 'scripts', 'stuck-bg') in r['hookSpecificOutput']['additionalContext'], r)
check('ledger: foreground bash ignored', bg({'hook_event_name': 'PostToolUse', 'tool_name': 'Bash', 'session_id': 'S1', 'tool_input': {'command': 'ls'}, 'tool_response': 'x'}) is None)
time.sleep(1.5)
r = bg({'hook_event_name': 'PreToolUse', 'tool_name': 'Read', 'session_id': 'S1', 'tool_input': {}})
check('ledger: overdue pushed on next tool call', r and 'overdue' in r['hookSpecificOutput']['additionalContext'], r)
check('ledger: not repeated within 60 s', bg({'hook_event_name': 'PreToolUse', 'tool_name': 'Read', 'session_id': 'S1', 'tool_input': {}}) is None)
check('ledger: other session not told', bg({'hook_event_name': 'PreToolUse', 'tool_name': 'Read', 'session_id': 'S2', 'tool_input': {}}) is None)
r = bg({'hook_event_name': 'Stop', 'session_id': 'S1'})
check('ledger: stop blocked once', r and r.get('decision') == 'block', r)
check('ledger: second stop passes', bg({'hook_event_name': 'Stop', 'session_id': 'S1'}) is None)
p = subprocess.run([os.path.join(CORE, 'scripts', 'stuck-bg'), 'done', 'all'], capture_output=True, text=True, timeout=10, env=ENV)
check('ledger: stuck-bg done all', '0 entries left' in p.stdout, p.stdout + p.stderr)

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
dev = os.path.join(FLUTTER, 'scripts', 'devctl')
out = subprocess.run([dev, 'status'], capture_output=True, text=True, timeout=15, env=ENV).stdout
check('devctl: empty status', 'no devices' in out, out)
p = subprocess.run([dev, 'build', '--', 'true'], capture_output=True, text=True, timeout=15, env=ENV)
check('devctl: build runs and auto-releases', p.returncode == 0 and 'released' in p.stdout, p.stdout + p.stderr)

shutil.rmtree(HOME, ignore_errors=True)
print(f'\n{"ALL PASS" if fails == 0 else f"{fails} FAILED"}')
sys.exit(1 if fails else 0)
