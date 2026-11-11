#!/usr/bin/env bash
# On-demand desktop, bound to the container network; host publishes loopback only.
# Access through a private SSH local forward, never through public Funnel.
set -euo pipefail
if [ "$#" -ne 0 ]; then
  if [ "$#" -ne 3 ] || [ "$1" != 'seat-review' ] || [ "$2" != '--date' ] || ! [[ "$3" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo 'Verwendung: login-private.sh [seat-review --date YYYY-MM-DD]' >&2
    exit 2
  fi
fi
umask 077
cd /app/server
export DISPLAY=:97
tmp=$(mktemp -d)
pids=()
cleanup() {
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  for pid in "${pids[@]}"; do wait "$pid" 2>/dev/null || true; done
  rm -rf "$tmp"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Do not steal an existing desktop or browser profile.
if [ -S /tmp/.X11-unix/X97 ]; then
  echo "Eine private Desktop-Sitzung läuft bereits." >&2
  exit 1
fi
password=$(/opt/agent-venv/bin/python -c 'import secrets,string; print("".join(secrets.choice(string.ascii_letters+string.digits) for _ in range(8)))')
x11vnc -storepasswd "$password" "$tmp/vnc.pass" >/dev/null
Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp -ac >"$tmp/xvfb.log" 2>&1 &
pids+=("$!")
for i in $(seq 1 30); do
  [ -S /tmp/.X11-unix/X97 ] && break
  sleep 0.2
done
test -S /tmp/.X11-unix/X97
x11vnc -display "$DISPLAY" -localhost -rfbport 5900 -rfbauth "$tmp/vnc.pass" -forever -shared -noxdamage -quiet >"$tmp/vnc.log" 2>&1 &
pids+=("$!")
websockify --web=/usr/share/novnc 0.0.0.0:6080 127.0.0.1:5900 >"$tmp/web.log" 2>&1 &
pids+=("$!")
sleep 1
for pid in "${pids[@]}"; do kill -0 "$pid"; done
printf '\nPrivater WESTbahn-Login: http://127.0.0.1:6080/vnc.html\nEinmaliges VNC-Passwort: %s\n' "$password"
printf 'Im Handy-Browser anmelden. Erst danach hier Enter drücken.\n\n'
if [ "$#" -eq 0 ]; then
  /opt/agent-venv/bin/python /app/server/browser/worker.py login
else
  /opt/agent-venv/bin/python /app/server/browser/worker.py "$@"
fi
