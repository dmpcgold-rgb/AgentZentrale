#!/usr/bin/env python3
"""Safely integrate PR #36's assigned-seat finder into the newer Oracle worker.

Does not check out, replace or merge the Git repository. Does not book.
"""
import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path("/opt/agentzentrale")
TARGET = REPO / "server/browser/worker.py"
REF = "refs/remotes/origin/pr-36:server/browser/worker.py"
FINDER = "def find_assigned_seat_link("
ENTRY = "\ndef open_review_seat_map("
OLD = """    change=find_seat_change_control(actual)
    if change is None:
        audit=find_seat_change_control(actual,diagnostic=True)
        raise Blocked('Ändern im Sitzplatzbereich nicht eindeutig. Diagnose: '+json.dumps(audit,ensure_ascii=False))
    change.click(timeout=5000)"""
NEW = """    change=find_seat_change_control(actual)
    if change is None:
        # Fall back only to the unique, visible link for the assigned seat.
        change=find_assigned_seat_link(actual)
    if change is None:
        audit={'change':find_seat_change_control(actual,diagnostic=True),
               'assignedSeat':find_assigned_seat_link(actual,diagnostic=True)}
        raise Blocked('Sitzplatzänderung nicht eindeutig. Diagnose: '+json.dumps(audit,ensure_ascii=False))
    change.click(timeout=5000)"""

def main():
    if os.geteuid() != 0:
        raise RuntimeError("Root-Rechte erforderlich.")
    source = subprocess.check_output(
        ["git", "-C", str(REPO), "show", REF], text=True
    )
    current = TARGET.read_text(encoding="utf-8")
    if FINDER in current:
        if NEW in current and "def live_seat_dry_run(" in current:
            print("PR36_BEREITS_INTEGRIERT")
            return
        raise RuntimeError("Teilweise Integration erkannt – keine Änderung.")
    assert source.count(FINDER) == 1, "PR-Quelle enthält keinen eindeutigen Finder"
    assert source.count(ENTRY) == 1, "PR-Quelle ist unerwartet"
    assert current.count(ENTRY) == 1, "Server-Entrypoint unerwartet"
    assert current.count(OLD) == 1, "Server-Änderungsstelle unerwartet"
    assert current.count("def live_seat_dry_run(") == 1, "Neuerer Servermodus fehlt"
    assert current.count("def unattended_seat_selection(") == 1, "Kaufsperre fehlt"
    helper = source[source.index(FINDER):source.index(ENTRY,source.index(FINDER))]
    ast.parse(helper)
    candidate = current.replace(ENTRY, "\n" + helper + ENTRY, 1)
    candidate = candidate.replace(OLD, NEW, 1)
    ast.parse(candidate)
    assert candidate.count("def unattended_seat_selection(") == 1
    assert "provider_absence_not_authoritative" in candidate
    backup = TARGET.with_name("worker.py.bak-pr36")
    if backup.exists():
        raise RuntimeError("Backup worker.py.bak-pr36 existiert bereits – nicht überschrieben.")
    shutil.copy2(TARGET, backup)
    temp = TARGET.with_name("worker.py.pr36-tmp")
    try:
        with temp.open("x", encoding="utf-8") as handle:
            handle.write(candidate)
            handle.flush()
            os.fsync(handle.fileno())
        shutil.copymode(TARGET, temp)
        os.replace(temp, TARGET)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    print("PR36_INTEGRIERT")
    print("BACKUP_OK")
    print("PYTHON_SYNTAX_OK")
    print("KAUFSPERRE_UNVERAENDERT")
    print("HINWEIS: Kein Docker-Neustart und keine Buchung durchgeführt.")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("INTEGRATION_BLOCKIERT:", str(error), file=sys.stderr)
        raise SystemExit(1)
