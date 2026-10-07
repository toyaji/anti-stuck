#!/bin/sh
# SessionStart hook — publish this pack where the anti-stuck core reads it:
#   ~/.anti-stuck/packs/flutter/{command-timeouts,route-rules,reap-patterns}.json
# route-rules.json gets this install's devctl path filled in, so the deny message names the exact command.
home="${ANTI_STUCK_HOME:-$HOME/.anti-stuck}"
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$home/packs/flutter"
cp "$root"/pack/command-timeouts.json "$root"/pack/reap-patterns.json "$home/packs/flutter"/ 2>/dev/null
sed "s#{{DEVCTL}}#$root/scripts/devctl#g" "$root/pack/route-rules.json" > "$home/packs/flutter/route-rules.json"
exit 0
