#!/usr/bin/env python3
"""Read latest PRIVATE Docker build log; emit categorised diagnostics ONLY."""
import os,re,sys
from pathlib import Path
if sys.argv[1:]!=['--diagnose'] or os.geteuid()!=0:
 print('BUILD_DIAG=BLOCKED_MODE');sys.exit(2)
root=Path('/root/agentzentrale-private-snapshots')
logs=sorted(root.glob('build-log-*'),key=lambda p:p.stat().st_mtime,reverse=True)
if not logs:
 print('BUILD_DIAG=NO_LOG');sys.exit(3)
raw=logs[0].read_text(encoding='utf-8',errors='replace')
tokens={
 'NODE_TEST_FAILURE':r'not ok [0-9]|node:internal/test_runner|FAIL[[:space:]]+test',
 'NODE_IMPORT_ERROR':r'ERR_MODULE_NOT_FOUND|Cannot find module',
 'NODE_SYNTAX_ERROR':r'SyntaxError:|Unexpected token',
 'PYTHON_TEST_FAILURE':r'FAILED \(|AssertionError:|unittest',
 'PYTHON_IMPORT_ERROR':r'ModuleNotFoundError:|ImportError:',
 'MISSING_FILE':r'not found|No such file or directory|ENOENT',
 'PERMISSIONS':r'Permission denied|EACCES',
 'PACKAGE_INSTALL':r'apt-get.*failed|pip install.*failed',
 'DOCKER_ERROR':r'failed to solve|ERROR: process',
}
for name,pattern in tokens.items():
 # Never print log details, file names, ticket details or source.
 print('DIAG_'+name+'='+('yes' if re.search(pattern.replace('[[:space:]]',r'\s'),raw,re.I) else 'no'))
# Allowlist the failing Dockerfile step, never arbitrary source or command.
step='UNKNOWN'
for line in raw.splitlines():
 if 'ERROR:' in line or 'failed to solve:' in line:
  if 'node --test' in line:step='NODE_TESTS'
  elif 'unittest' in line:step='PYTHON_TESTS'
  elif 'compileall' in line:step='PYTHON_COMPILE'
  elif 'pip install' in line:step='PIP'
  elif 'apt-get' in line:step='APT'
  elif 'COPY' in line:step='COPY'
print('BUILD_FAILURE_STEP='+step)
# Test descriptions are printed only when they exactly match public Node tests
# copied into the private stage; never emit arbitrary Docker log text.
known=set()
stage=Path('/root/agentzentrale-private-staging')
copies=[p for p in stage.glob('source-*/code/server/tests') if p.is_dir()]
if copies:
 tests=max(copies,key=lambda p:p.parent.parent.stat().st_mtime)
 for name in ('gmail-audit.test.mjs','westbahn.test.mjs','browser_audit.test.mjs',
              'browser_route.test.mjs','weekly-review.test.mjs',
              'booking-readiness.test.mjs','trip-preview.test.mjs'):
  f=tests/name
  if f.is_file():
   for title in re.findall(r"""test\\(['"]([^'"]{1,120})['"]""",f.read_text(encoding='utf-8')):
    known.add(title)
fails=re.findall(r'(?m)^.*?\\bnot ok \\d+ - ([^\\r\\n]+)',raw)
print('NODE_FAILED_TEST_COUNT='+str(len(fails)))
for i,title in enumerate(fails[:8],1):
 print('FAILED_PUBLIC_TEST_'+str(i)+'='+title if title in known else 'FAILED_PUBLIC_TEST_'+str(i)+'=UNMATCHED')
print('NODE_ASSERTION_ERROR='+('yes' if 'ERR_ASSERTION' in raw else 'no'))
print('NODE_TESTCODE_FAILURE='+('yes' if 'testCodeFailure' in raw else 'no'))
print('BUILD_DIAG=COMPLETE')
