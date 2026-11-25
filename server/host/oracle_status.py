"""Narrow host control worker. No network listener, no arbitrary commands."""
import json, os, subprocess, time, stat
from pathlib import Path
from datetime import datetime, timezone

TIMER = "westbahn-booking.timer"
SERVICE = "westbahn-booking.service"
ROOT = Path(os.environ.get("ORACLE_CONTROL_DIR", "/var/lib/agentzentrale-control"))
ACTIONS = {"pause": ["disable", "--now", TIMER],
           "resume": ["enable", "--now", TIMER]}
def ctl(*args):
    return subprocess.run(["/usr/bin/systemctl", *args], capture_output=True,
                          text=True, timeout=20, check=False)
def snapshot():
    def props(unit, names):
        result = ctl("show", unit, *["--property="+n for n in names])
        if result.returncode: raise RuntimeError("systemd unavailable")
        return dict(line.split("=",1) for line in result.stdout.splitlines() if "=" in line)
    return {"timestamp": datetime.now(timezone.utc).isoformat(),
            "timer": props(TIMER, ["ActiveState","UnitFileState","NextElapseUSecRealtime"]),
            "service": props(SERVICE, ["ActiveState","SubState","Result"])}
def publish(name, value):
    tmp = ROOT / (name+".tmp")
    fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o640)
    with os.fdopen(fd,"w") as f: json.dump(value,f)
    os.replace(tmp,ROOT/name)
def main():
    # Directory and ownership must be provisioned by host administrator.
    # No secret or checkout script is shared with the gateway.
    publish("status.json", snapshot())
    # Deliberately no booking-start action until the binding-price gate is verified.
if __name__ == "__main__":
    main()
