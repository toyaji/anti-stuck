#!/bin/sh
# SessionStart hook — publish this pack where the anti-stuck core reads it:
#   ~/.anti-stuck/packs/flutter/{command-timeouts,route-rules,reap-patterns}.json
#   ~/.anti-stuck/bin/devctl -> <installed plugin>/scripts/devctl (tlimit puts ~/.anti-stuck/bin on PATH)
home="${ANTI_STUCK_HOME:-$HOME/.anti-stuck}"
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$home/packs/flutter" "$home/bin"
cp "$root"/pack/*.json "$home/packs/flutter"/ 2>/dev/null
printf '#!/bin/sh\nexec python3 "%s/scripts/devctl" "$@"\n' "$root" > "$home/bin/devctl"
chmod +x "$home/bin/devctl"
exit 0
