"""Host-only worker; narrow requests, no network listener or arbitrary commands."""
import json, os, subprocess, tempfile, re, stat, fcntl
from pathlib import Path
from datetime import datetime, timezone

TIMER = "westbahn-booking.timer"
SERVICE = "westbahn-booking.service"
ROOT = Path(os.environ.get("ORACLE_CONTROL_DIR", "/var/lib/agentzentrale-control"))
PRIVATE = Path(os.environ.get("ORACLE_BOOKING_DIR", "/opt/agentzentrale/westbahn-stable"))
DROPIN = Path("/etc/systemd/system/westbahn-booking.timer.d/90-agentzentrale-schedule.conf")
ACTIONS = {"pause": ["disable", "--now", TIMER], "resume": ["enable", "--now", TIMER]}
def ctl(*args):
    return subprocess.run(["/usr/bin/systemctl", *args], capture_output=True,
                          text=True, timeout=20, check=True)
def publish(path, value, mode=0o644):
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,"w") as f:
            os.fchmod(f.fileno(),mode)
            json.dump(value,f)
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)
def snapshot():
    def props(unit, names):
        result = ctl("show", unit, *["--property="+n for n in names])
        return dict(line.split("=",1) for line in result.stdout.splitlines() if "=" in line)
    return {"timestamp":datetime.now(timezone.utc).isoformat(),
            "timer":props(TIMER,["ActiveState","UnitFileState","NextElapseUSecRealtime"]),
            "service":props(SERVICE,["ActiveState","SubState","Result"]),
            "telegramConfigured":all((PRIVATE/n).is_file() for n in ("telegram.token","telegram.chat_id"))}
def apply(command):
    action=command.get("action")
    if action in ACTIONS:
        ctl(*ACTIONS[action])
    elif action=="schedule":
        hour=command.get("time")
        if not isinstance(hour,str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",hour): raise ValueError("invalid time")
        if ctl("is-active", TIMER).stdout.strip()!="active": raise ValueError("timer must be active")
        DROPIN.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        previous=DROPIN.read_bytes() if DROPIN.exists() else None
        def write(text):
            fd,name=tempfile.mkstemp(dir=DROPIN.parent)
            with os.fdopen(fd,"wb") as f:
                os.fchmod(f.fileno(),0o644); f.write(text)
            os.replace(name,DROPIN)
        try:
            write(("[Timer]\nOnCalendar=\nOnCalendar=Mon *-*-* "+hour+":00 Europe/Vienna\n").encode())
            ctl("daemon-reload"); ctl("restart",TIMER)
        except Exception:
            if previous is None: DROPIN.unlink(missing_ok=True)
            else: write(previous)
            ctl("daemon-reload"); ctl("restart",TIMER)
            raise
    else: raise ValueError("unsupported action")
def process():
    inbox=ROOT/"inbox"
    for path in sorted(inbox.glob("*.json"))[:10]:
        if not re.fullmatch(r"[0-9a-f-]{36}\.json",path.name): continue
        try:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,"rb") as f:
                info=os.fstat(f.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size>2048: raise ValueError("invalid file")
                command=json.loads(f.read(2049))
            path.unlink()
            if command.get("id")!=path.stem: raise ValueError("invalid id")
            age=datetime.now(timezone.utc).timestamp()-float(command.get("created",0))
            if not 0<=age<=120: raise ValueError("expired")
            apply(command)
            ok=True
        except Exception:
            path.unlink(missing_ok=True); ok=False
        publish(ROOT/"out"/(path.stem+".json"),{"id":path.stem,"ok":ok})
def main():
    # Root-owned out directory, separate writable inbox. No secrets shared.
    with open(ROOT/"worker.lock","a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if os.environ.get("ORACLE_CONTROL_ENABLED")=="1": process()
        publish(ROOT/"out"/"status.json",snapshot())
        try:
            report=json.loads((PRIVATE/"reports/latest.json").read_text())
            keys=("erstellt","dienst_status","bereits_gebucht","neu_gebucht","gesamt_bestaetigt","lueckenlos_bis","offene_gepruefte_tage","fehler_oder_luecken")
            publish(ROOT/"out"/"report.json",{k:report[k] for k in keys})
        except (OSError,ValueError,KeyError):
            (ROOT/"out"/"report.json").unlink(missing_ok=True)
if __name__=="__main__": main()
