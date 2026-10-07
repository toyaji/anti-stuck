#!/bin/bash
# Stop / SubagentStop hook — kill runaway processes that sessions leave behind. Only these patterns:
#  1) orphaned flutter_tester (ppid 1) — its test runner is gone
#  2) flutter_tester older than 30 min
#  3) whole-disk searches (find / ..., grep -r ... /) older than 5 min
# flutter run, dev servers and anything the user started are never touched.
HOME_DIR="${FAS_HOME:-$HOME/.flutter-anti-stuck}"
mkdir -p "$HOME_DIR/logs"
LOG="$HOME_DIR/logs/reap.log"
now=$(date '+%F %T')
secs() { # ps etime([[dd-]hh:]mm:ss) -> seconds
  awk -v t="$1" 'BEGIN{d=0; if (index(t,"-")) {split(t,a,"-"); d=a[1]; t=a[2]}
    n=split(t,p,":"); s=0; for(i=1;i<=n;i++) s=s*60+p[i]; print d*86400+s}'
}
ps -eo pid=,ppid=,etime=,command= | while read -r pid ppid etime cmd; do
  age=$(secs "$etime"); why=""
  case "$cmd" in
    *flutter_tester*)
      if [ "$ppid" = 1 ]; then why="orphaned flutter_tester"
      elif [ "$age" -gt 1800 ]; then why="flutter_tester older than 30 min"; fi ;;
    *"find / "*|*"grep -r"*" / "*)
      case "$cmd" in find*) [ "$age" -gt 300 ] && why="whole-disk search older than 5 min";; esac ;;
  esac
  if [ -n "$why" ]; then
    kill "$pid" 2>/dev/null && echo "$now kill $pid ($why, ${etime}) ${cmd:0:160}" >> "$LOG"
  fi
done
exit 0
