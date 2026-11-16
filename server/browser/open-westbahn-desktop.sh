#!/bin/sh
# Open the official WESTbahn page in the existing private noVNC Chromium desktop.
# This does not click booking controls, submit credentials or make purchases.
set -eu
URL='https://westbahn.at/reservierung/sitzplatz-upgrade/'
export DISPLAY=:99
export XDG_RUNTIME_DIR=/tmp/westbahn-runtime
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"
if ! pgrep -f 'Xvfb :99 ' >/dev/null 2>&1; then
  echo 'ERROR: Private desktop :99 is not running. Start the private review first.' >&2
  exit 1
fi
if ! pgrep -f 'x11vnc.*-display :99' >/dev/null 2>&1; then
  echo 'ERROR: Private VNC is not running.' >&2
  exit 1
fi
PROFILE=/tmp/westbahn-vnc-chrome
mkdir -p "$PROFILE"
chmod 700 "$PROFILE"
# Chromium forwards a new URL to an existing instance with this profile.
# Otherwise it starts a new visible browser on the private virtual desktop.
chromium --no-sandbox --disable-dev-shm-usage --no-first-run \
  --user-data-dir="$PROFILE" --window-size=1280,900 \
  "$URL" >/tmp/westbahn-vnc-chrome-open.log 2>&1 &
echo 'WESTBAHN_BROWSER_OPEN_REQUESTED'
echo 'Use the existing private SSH tunnel and /vnc.html. No booking was made.'
