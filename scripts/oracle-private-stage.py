#!/usr/bin/env python3
"""Create an isolated, root-private staging copy from verified Oracle backup.

Never change /opt/agentzentrale, its running Docker container or Git history.
Never upload or print source, credentials, ticket details, or source filenames.
"""
import ast
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile

def stop(message):
    print("STAGE_BLOCKED=" + message, file=sys.stderr)
    raise SystemExit(2)

if sys.argv[1:] != ["--stage"]:
    stop("invalid_mode")
if os.geteuid() != 0:
    stop("requires_root")

root = Path("/root/agentzentrale-private-snapshots")
if not root.is_dir():
    stop("backup_root_missing")
candidates = [p for p in root.glob("reconcile-*")
              if p.is_dir() and (p / "SHA256SUMS").is_file()
              and (p / "source/oracle-worktree.tgz").is_file()]
if not candidates:
    stop("reconcile_backup_missing")
latest = max(candidates, key=lambda p: p.stat().st_mtime)
verify = subprocess.run(["sha256sum", "--quiet", "-c", "SHA256SUMS"],
                        cwd=latest, capture_output=True)
if verify.returncode:
    stop("snapshot_checksum_failed")

staging_root = Path("/root/agentzentrale-private-staging")
staging_root.mkdir(mode=0o700, parents=True, exist_ok=True)
os.chmod(staging_root, 0o700)
output = Path(tempfile.mkdtemp(prefix="source-", dir=staging_root))
os.chmod(output, 0o700)
code = output / "code"
code.mkdir(mode=0o700)
max_file_bytes = 6 * 1024 * 1024
max_total_bytes = 120 * 1024 * 1024
total_bytes = 0
source_count = 0
skipped = 0

def destination_for(path):
    parts = PurePosixPath(path).parts
    if (not parts or any(part in ("", ".", "..") for part in parts)
            or path.startswith("/")):
        stop("unsafe_archive_path")
    return code.joinpath(*parts)

def private_filename(path):
    parts = [p.lower() for p in PurePosixPath(path).parts]
    return any(p == ".git" or p == "data" or p == ".ssh"
               or p == ".env" or p.startswith(".env.")
               or p.endswith((".pem", ".key", ".p12", ".jks", ".keystore"))
               or p in ("credentials.json", "google-services.json")
               for p in parts)

with tarfile.open(latest / "source/oracle-worktree.tgz", "r:gz") as archive:
    for member in archive:
        dst = destination_for(member.name)
        if private_filename(member.name):
            skipped += 1
            continue
        if member.isdir():
            dst.mkdir(mode=0o700, parents=True, exist_ok=True)
            continue
        if not member.isfile():  # no symbolic/hard links or special files
            skipped += 1
            continue
        if member.size > max_file_bytes:
            stop("source_file_size_exceeded")
        total_bytes += member.size
        if total_bytes > max_total_bytes:
            stop("total_source_size_exceeded")
        dst.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        src = archive.extractfile(member)
        if src is None:
            stop("source_extraction_failed")
        with dst.open("wb") as fd:
            shutil.copyfileobj(src, fd)
        os.chmod(dst, 0o600)
        source_count += 1

checkout = latest / "container-browser"
files = sorted(checkout.glob("*.py"))
expected = {"ticketshop_station_dry_run.py"} | {
    "checkout_202611" + str(d) + ".py" for d in range(23, 28)
}
if {p.name for p in files} != expected:
    stop("checkout_files_missing_or_extra")
target = code / "server/browser"
target.mkdir(mode=0o700, parents=True, exist_ok=True)
for file in files:
    data = file.read_bytes()
    if len(data) > max_file_bytes:
        stop("checkout_file_size_exceeded")
    ast.parse(data.decode("utf-8"), filename=file.name)
    (target / file.name).write_bytes(data)
    os.chmod(target / file.name, 0o600)

for necessary in ("Dockerfile", "compose.yaml", "server/index.mjs",
                  "server/browser/worker.py", "server/browser/requirements.txt"):
    if not (code / necessary).is_file():
        stop("required_source_missing")

py_checked = 0
for p in code.rglob("*.py"):
    ast.parse(p.read_text(encoding="utf-8"), filename=p.name)
    py_checked += 1

print("PRIVATE_STAGE_COMPLETE")
print(f"SOURCE_FILES_STAGED={source_count}")
print(f"PRIVATE_PATHS_EXCLUDED={skipped}")
print(f"CHECKOUT_FILES_STAGED={len(files)}")
print(f"PYTHON_FILES_VALIDATED={py_checked}")
print("SNAPSHOT_CHECKSUMS=OK")
print("STAGED_SOURCE_ONLY_ON_ORACLE=yes")
print("PRODUCTION_FILES_MODIFIED=no")
print("LIVE_CONTAINER_RESTARTED=no")
print("NO_BOOKINGS_EXECUTED=yes")
print("NO_DEPLOYMENT_EXECUTED=yes")
print("NO_PRIVATE_SOURCE_UPLOADED=yes")
print("APPLY_STILL_BLOCKED=yes")
