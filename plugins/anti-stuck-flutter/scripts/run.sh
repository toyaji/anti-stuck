#!/bin/sh
# Hook launcher: run.sh <script> — run a hook script that sits next to this file.
# A missing script must never block tools: python's "can't open file" exits 2, which Claude Code
# reads as "block this call". So a missing script passes (exit 0) with a warning instead.
dir="$(cd "$(dirname "$0")" && pwd)"
script="$dir/$1"
if [ ! -f "$script" ]; then
  echo "anti-stuck: hook script missing ($script) — skipped. Reinstall or reload the plugin." >&2
  exit 0
fi
case "$script" in
  *.py) exec python3 "$script" ;;
  *) exec sh "$script" ;;
esac
