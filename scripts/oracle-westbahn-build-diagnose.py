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
print('BUILD_DIAG=COMPLETE')
