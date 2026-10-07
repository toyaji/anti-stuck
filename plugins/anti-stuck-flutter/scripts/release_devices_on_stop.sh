#!/bin/bash
# Stop hook — when this session goes idle, hand back the devices it holds. Apps keep running:
# the next waiter takes them over, or they stay up as "free" for any session to reuse.
HOME_DIR="${ANTI_STUCK_HOME:-$HOME/.anti-stuck}"
mkdir -p "$HOME_DIR/logs"
out=$("$(cd "$(dirname "$0")" && pwd)/anti-stuck-flutter" release-all 2>&1)
[ -n "$out" ] && echo "$(date '+%F %T') $out" >> "$HOME_DIR/logs/device-release.log"
exit 0
