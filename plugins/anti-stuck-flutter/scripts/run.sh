#!/bin/sh
# Hook launcher: run.sh <script path> — run one hook script with a working Python 3.
# A missing script or interpreter must never block tools: python's "can't open file" exits 2, which
# Claude Code reads as "block this call". Both cases pass (exit 0) with a warning instead.
export PYTHONUTF8=1
script="$1"
if [ ! -f "$script" ]; then
  echo "anti-stuck: hook script missing ($script) — skipped. Reinstall or reload the plugin." >&2
  exit 0
fi
case "$script" in
  *.py) ;;
  *) exec sh "$script" ;;
esac
for py in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    exec "$py" "$script"
  fi
done
echo "anti-stuck: no Python 3.8+ found (tried python3.13 … python3, python) — hook skipped." >&2
exit 0
