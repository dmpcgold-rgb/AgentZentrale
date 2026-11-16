#!/bin/sh
# Private WESTbahn visual seat review. Access ONLY via SSH tunnel to host 127.0.0.1:6080.
set -eu
DAY="${1:-}"
case "$DAY" in
  ????-??-??) ;;
  *) echo "Usage: start-private-seat-review.sh YYYY-MM-DD" >&2; exit 2 ;;
esac
export DISPLAY=:99
export XDG_RUNTIME_DIR=/tmp/westbahn-runtime
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
# A dedicated virtual screen; the web UI must never be exposed directly to the Internet.
if ! pgrep -f 'Xvfb :99 ' >/dev/null 2>&1; then
  Xvfb :99 -screen 0 1280x900x24 -nolisten tcp >/tmp/westbahn-xvfb.log 2>&1 &
fi
sleep 2
if ! pgrep -f 'x11vnc.*-display :99' >/dev/null 2>&1; then
  x11vnc -display :99 -localhost -nopw -forever -shared -rfbport 5900 >/tmp/westbahn-vnc.log 2>&1 &
fi
if ! pgrep -f 'websockify.*6080' >/dev/null 2>&1; then
  websockify --web=/usr/share/novnc 0.0.0.0:6080 localhost:5900 >/tmp/westbahn-websockify.log 2>&1 &
fi
echo "PRIVATE_DESKTOP_READY: SSH tunnel to 127.0.0.1:6080; open http://127.0.0.1:6080/vnc.html"
echo "The review browser can select/confirm a seat, but it must not purchase a ticket."
exec /opt/agent-venv/bin/python /tmp/westbahn-trip/server/browser/worker.py seat-review --date "$DAY"
