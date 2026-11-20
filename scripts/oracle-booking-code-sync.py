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
# Accept the entire public application code bundle, not just five updated
# files: a partially updated codebase can fail with ESM named-export errors.
# Never accept paths outside the public Docker build context.
def public_build_source(name):
    parts=name.split("/")
    if not parts or any(p in ("", ".", "..") for p in parts):
        return False
    if name in ("Dockerfile","package.json"):
        return True
    if parts[0]=="server" and len(parts)>=2:
        if any(p.startswith(".") or p in ("data","node_modules","__pycache__") for p in parts):
            return False
        # Dated checkout scripts MUST remain Oracle-only, even if mistakenly
        # committed to a public branch.
        if parts[-1].startswith("checkout_") or parts[-1]=="ticketshop_station_dry_run.py":
            return False
        return name.endswith((".mjs",".js",".json",".py",".txt",".html",".css"))
    return (len(parts)>=3 and parts[:2]==["src","core"] and
            name.endswith((".js",".mjs",".json")))

blob=sys.stdin.buffer.read(5000000)
if not blob or len(blob)>4500000: blocked("INVALID_INPUT_SIZE")
try:
    with tarfile.open(fileobj=io.BytesIO(blob),mode="r:") as t:
        members=t.getmembers()
        names=[m.name for m in members]
        if not members or len(names)!=len(set(names)):
            blocked("DUPLICATE_OR_EMPTY_ARCHIVE")
        if any(not public_build_source(m.name) or not m.isfile() or
               m.size>300000 for m in members):
            blocked("UNEXPECTED_OR_UNSAFE_FILES")
        data={m.name:t.extractfile(m).read() for m in members}
except (tarfile.TarError,OSError,AttributeError):
    blocked("INVALID_ARCHIVE")
essential={"Dockerfile","package.json","server/index.mjs","server/westbahn.mjs",
           "server/gmail-audit.mjs","server/tests/westbahn.test.mjs",
           "server/tests/gmail-audit.test.mjs","src/core/westbahn.js"}
if not essential.issubset(data): blocked("REQUIRED_PUBLIC_FILES_MISSING")

output=Path(tempfile.mkdtemp(prefix="source-",dir=root))
os.chmod(output,0o700)
try:
    shutil.copytree(latest/"code",output/"code",symlinks=False)
    for name in data:
        target=output/"code"/name
        if target.is_symlink(): blocked("SYMLINK_TARGET")
    for name,content in data.items():
        target=output/"code"/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o600)
    # The Oracle HOST may not have Node installed. The PRIVATE Dockerfile runs
    # the full Node test suite during docker build, before any rollout.
    for name in essential:
        if not (output/"code"/name).is_file():
            blocked("EXPECTED_SOURCE_MISSING")
except OSError:
    blocked("STAGE_PREPARATION_FAILED")
print("BOOKING_STAGE=READY")
print("BOOKING_STAGE_SOURCE=READY_FOR_DOCKER_TESTS")
print("PRIVATE_CHECKOUT_PRESERVED=yes")
print("PUBLIC_BUILD_CONTEXT_SYNCHRONIZED=yes")
print("PRODUCTION_FILES_MODIFIED=no")
print("NO_BOOKINGS_EXECUTED=yes")
