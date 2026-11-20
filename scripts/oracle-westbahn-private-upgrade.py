#!/usr/bin/env python3
"""Overlay only reviewed public WESTbahn files onto a copy of Oracle's private staging."""
import os,sys,tarfile,shutil,tempfile,ast
from pathlib import Path
if sys.argv[1:]!=['--refresh'] or os.geteuid()!=0:
 print('UPGRADE_STAGE=BLOCKED_MODE_OR_USER');sys.exit(2)
root=Path('/root/agentzentrale-private-staging')
incoming=root/'westbahn-public-overlay.tar.gz'
allowed={
 'server/westbahn.mjs','server/index.mjs','server/gmail-audit.mjs',
 'server/tests/westbahn.test.mjs','server/tests/gmail-audit.test.mjs'
}
if not incoming.is_file():
 print('UPGRADE_STAGE=BLOCKED_OVERLAY_MISSING');sys.exit(3)
candidates=[p for p in root.glob('source-*') if (p/'code/Dockerfile').is_file() and (p/'code/server/browser/checkout_20261125.py').is_file()]
if not candidates:
 print('UPGRADE_STAGE=BLOCKED_PRIVATE_STAGE_MISSING');sys.exit(3)
source=max(candidates,key=lambda p:p.stat().st_mtime)
# Refuse unsafe, unexpected, missing, symlink or huge public additions.
with tarfile.open(incoming,'r:gz') as archive:
 members=archive.getmembers()
 names={m.name.removeprefix('./') for m in members if m.isfile()}
 if names!=allowed or len(members)>len(allowed)+5:
  print('UPGRADE_STAGE=BLOCKED_PUBLIC_ALLOWLIST');sys.exit(3)
 if any((m.issym() or m.islnk() or not(m.isfile() or m.isdir()) or m.size>500000) for m in members):
  print('UPGRADE_STAGE=BLOCKED_ARCHIVE_TYPE');sys.exit(3)
 out=Path(tempfile.mkdtemp(prefix='source-',dir=root))
 os.chmod(out,0o700)
 try:
  shutil.copytree(source/'code',out/'code',symlinks=False)
  for m in members:
   if not m.isfile():continue
   name=m.name.removeprefix('./')
   dst=out/'code'/name
   if not dst.is_file() or dst.is_symlink():
    raise ValueError('public source path missing or symlink')
   stream=archive.extractfile(m)
   if stream is None:raise ValueError('archive member unreadable')
   dst.write_bytes(stream.read())
   os.chmod(dst,0o600)
  # Private checkout files must still exist and parse successfully.
  browser=out/'code/server/browser'
  for n in ['ticketshop_station_dry_run.py',*[f'checkout_202611{d}.py' for d in range(23,28)]]:
   ast.parse((browser/n).read_text('utf-8'),filename=n)
  # Verify public source is not executable script injections via archive names;
  # Node unit tests will run inside the Docker candidate build.
 except Exception:
  shutil.rmtree(out,ignore_errors=True)
  print('UPGRADE_STAGE=BLOCKED_VALIDATION_FAILED');sys.exit(3)
print('UPGRADE_STAGE=OK')
print('PUBLIC_FILES_OVERLAID=5')
print('PRIVATE_CHECKOUT_FILES_RETAINED=6')
print('NO_DEPLOYMENT_EXECUTED=yes')
print('NO_BOOKINGS_EXECUTED=yes')
