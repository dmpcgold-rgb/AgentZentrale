#!/usr/bin/env python3
"""Apply three public, reviewed booking fixes to a new PRIVATE Oracle stage.
Reads an allowlisted tar stream from GitHub Actions; no production mutation.
"""
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

def blocked(code):
    print("BOOKING_STAGE=BLOCKED_"+code)
    raise SystemExit(3)

if sys.argv[1:] != ["--booking-code-sync"] or os.geteuid()!=0:
    blocked("INVALID_INVOCATION")
root=Path("/root/agentzentrale-private-staging")
if not root.is_dir(): blocked("PRIVATE_STAGE_MISSING")
stages=[p for p in root.glob("source-*") if p.is_dir() and (p/"code"/"Dockerfile").is_file()]
if not stages: blocked("PRIVATE_STAGE_MISSING")
latest=max(stages,key=lambda p:p.stat().st_mtime)
allowed={"server/westbahn.mjs","server/index.mjs","server/gmail-audit.mjs",
         "server/tests/westbahn.test.mjs","server/tests/gmail-audit.test.mjs"}
blob=sys.stdin.buffer.read(350000)
if not blob or len(blob)>300000: blocked("INVALID_INPUT_SIZE")
try:
    with tarfile.open(fileobj=io.BytesIO(blob),mode="r:") as t:
        members=t.getmembers()
        if {m.name for m in members}!=allowed or len(members)!=len(allowed):
            blocked("UNEXPECTED_FILES")
        if any(not m.isfile() or m.size>110000 for m in members):
            blocked("UNSAFE_ARCHIVE")
        data={m.name:t.extractfile(m).read() for m in members}
except (tarfile.TarError,OSError,AttributeError):
    blocked("INVALID_ARCHIVE")
output=Path(tempfile.mkdtemp(prefix="source-",dir=root))
os.chmod(output,0o700)
try:
    shutil.copytree(latest/"code",output/"code",symlinks=False)
    for name,content in data.items():
        target=output/"code"/name
        if not target.is_file(): blocked("EXPECTED_SOURCE_MISSING")
        target.write_bytes(content)
        target.chmod(0o600)
    # Run all Node tests before the private image is built.
    test=subprocess.run(["node","--test","server/tests/westbahn.test.mjs",
        "server/tests/gmail-audit.test.mjs"],cwd=output/"code",
        capture_output=True,timeout=90)
    if test.returncode: blocked("NODE_TESTS_FAILED")
except (OSError,subprocess.TimeoutExpired):
    blocked("STAGE_PREPARATION_FAILED")
print("BOOKING_STAGE=READY")
print("BOOKING_TESTS=PASS")
print("PRIVATE_CHECKOUT_PRESERVED=yes")
print("PRODUCTION_FILES_MODIFIED=no")
print("NO_BOOKINGS_EXECUTED=yes")
