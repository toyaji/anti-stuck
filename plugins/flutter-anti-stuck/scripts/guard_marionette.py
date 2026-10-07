#!/usr/bin/env python3
"""PreToolUse(mcp__marionette__*) — fail fast instead of hanging when the app or the previous connection is gone.

Marionette MCP calls wait as long as the server does. This hook checks in 3 s:
- connect: the target VM answers getVersion. If the previously connected app is still running per the devctl
  ledger but its VM is silent (paused, e.g. iOS backgrounded), connect would hang closing it -> block
- disconnect: forget the remembered connection
- any other tool: the remembered VM answers, and on Android the app is in the foreground
The hard stop for a hung server is the MCP timeout (see README); this hook only turns known hangs into fast errors.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

HOME = os.environ.get('FAS_HOME') or os.path.expanduser('~/.flutter-anti-stuck')
STATE = os.path.join(HOME, 'state', 'marionette_last_uri')
LEDGER = os.path.join(HOME, 'state', 'devices', 'ledger.json')
TIMEOUT = 3
IOS_UDID = re.compile(r'[0-9A-F]{8}-[0-9A-F]{16}|[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}')


def block(msg):
    print(f'[flutter-anti-stuck: marionette] {msg}', file=sys.stderr)
    sys.exit(2)


def http_base(ws_uri):
    m = re.match(r'wss?://([^/]+)/(.*?)/?ws/?$', ws_uri or '')
    return f'http://{m.group(1)}/{m.group(2)}/' if m else None


def vm_alive(ws_uri):
    base = http_base(ws_uri)
    if not base:
        return False
    try:
        with urllib.request.urlopen(base + 'getVersion', timeout=TIMEOUT) as r:
            return b'"Version"' in r.read()
    except Exception:
        return False


def ledger_devices():
    try:
        return json.load(open(LEDGER)).get('devices', {})
    except Exception:
        return {}


def app_in_ledger(ws_uri):
    return any((d.get('app') or {}).get('ws') == ws_uri for d in ledger_devices().values())


def android_app_of(ws_uri):
    for key, d in ledger_devices().items():
        app = d.get('app') or {}
        if app.get('ws') == ws_uri and not IOS_UDID.fullmatch(key):
            return key, app
    return None, None


def android_package(app):
    override = os.environ.get('CLAUDE_PLUGIN_OPTION_ANDROID_PACKAGE')
    if override:
        return override
    cwd = (app or {}).get('cwd') or ''
    for name in ('build.gradle.kts', 'build.gradle'):
        try:
            src = open(os.path.join(cwd, 'android', 'app', name)).read()
        except OSError:
            continue
        m = re.search(r'applicationId\s*=?\s*["\']([\w.]+)["\']', src)
        if m:
            return m.group(1)
    return None


def android_foreground(key, package):
    try:
        out = subprocess.run(['adb', '-s', key, 'shell', 'dumpsys', 'activity', 'activities'],
                             capture_output=True, text=True, timeout=TIMEOUT).stdout
    except Exception:
        return True  # cannot check -> do not block
    resumed = [l for l in out.splitlines() if 'mResumedActivity' in l or 'topResumedActivity' in l]
    return any(package in l for l in resumed) if resumed else True


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool = data.get('tool_name', '')
    m = re.match(r'mcp__(?:plugin_.*_)?marionette__(\w+)$', tool)
    if not m:
        return
    name = m.group(1)
    if name == 'disconnect':
        if os.path.exists(STATE):
            os.remove(STATE)
        return
    if name == 'connect':
        uri = (data.get('tool_input') or {}).get('uri', '')
        if not vm_alive(uri):
            block(f'The VM at {uri} did not answer within {TIMEOUT} s. The app is gone or frozen — check `devctl status`.')
        prev = open(STATE).read().strip() if os.path.exists(STATE) else ''
        if prev and prev != uri and app_in_ledger(prev) and not vm_alive(prev):
            block(f'The previously connected app ({prev}) is still running but its VM is silent (paused). connect closes '
                  'that connection first and would hang. Bring that app to the foreground, or stop it with '
                  '`devctl stop <device>`, then disconnect and connect again.')
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        open(STATE, 'w').write(uri)
        return
    uri = open(STATE).read().strip() if os.path.exists(STATE) else ''
    if not uri:
        return
    if not vm_alive(uri):
        block(f'The connected app ({uri}) VM did not answer within {TIMEOUT} s. Check `devctl status` before connecting again.')
    key, app = android_app_of(uri)
    package = android_package(app) if key else None
    if key and package and name not in ('hot_reload', 'hot_restart') and not android_foreground(key, package):
        block(f'On Android ({key}) the app {package} is not in the foreground. Marionette calls hang in this state — '
              'ask the user to bring the app to the front.')


if __name__ == '__main__':
    main()
