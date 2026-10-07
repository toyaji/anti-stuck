#!/bin/sh
# SessionStart hook — write a stable launcher for this plugin's command-line tool:
# ~/.anti-stuck/bin/stuck-bg -> <installed plugin>/scripts/stuck-bg. tlimit puts ~/.anti-stuck/bin on PATH.
home="${ANTI_STUCK_HOME:-$HOME/.anti-stuck}"
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$home/bin"
printf '#!/bin/sh\nexec "%s/scripts/stuck-bg" "$@"\n' "$root" > "$home/bin/stuck-bg"
chmod +x "$home/bin/stuck-bg"
exit 0
