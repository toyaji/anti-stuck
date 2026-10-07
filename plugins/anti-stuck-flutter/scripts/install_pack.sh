#!/bin/sh
# SessionStart hook — publish this pack's rules where the anti-stuck core reads them:
# ~/.anti-stuck/packs/flutter/{command-timeouts,route-rules,reap-patterns}.json
home="${ANTI_STUCK_HOME:-$HOME/.anti-stuck}"
src="$(cd "$(dirname "$0")/.." && pwd)/pack"
dst="$home/packs/flutter"
mkdir -p "$dst" && cp "$src"/*.json "$dst"/ 2>/dev/null
exit 0
