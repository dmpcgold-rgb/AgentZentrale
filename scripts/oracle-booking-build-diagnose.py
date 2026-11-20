#!/usr/bin/env python3
"""Classify last private Docker build failure without exposing log lines."""
import glob,os,re,sys
from pathlib import Path
if sys.argv[1:]!=['--booking-diagnose'] or os.geteuid()!=0:
 print('BUILD_DIAGNOSIS=BLOCKED_INVALID_MODE');sys.exit(3)
files=[Path(p) for p in glob.glob('/root/agentzentrale-private-snapshots/build-log-*') if Path(p).is_file()]
if not files:
 print('BUILD_DIAGNOSIS=BLOCKED_NO_PRIVATE_LOG');sys.exit(3)
p=max(files,key=lambda p:p.stat().st_mtime)
raw=p.read_text(encoding='utf-8',errors='replace')[-200000:]
# Only boolean categories, never quote raw lines, test names, private source or credentials.
categories={
 'NODE_TEST_ASSERTION':r'(?m)^.*(?:not ok [0-9]+|ERR_ASSERTION|AssertionError).*$',
 'NODE_MODULE_LOAD':r'ERR_MODULE_NOT_FOUND|Cannot find module|ERR_PACKAGE_PATH_NOT_EXPORTED',
 'NODE_SYNTAX':r'SyntaxError:|Unexpected token',
 'PYTHON_TEST':r'FAILED \(|Traceback \(most recent call last\)|ModuleNotFoundError:',
 'APT_INSTALL':r'(?:E: Unable to locate package|apt-get.*returned a non-zero|Failed to fetch)',
 'PIP_INSTALL':r'(?:ERROR: Could not find a version|pip install.*did not run successfully)',
 'DOCKER_BUILD_CONTEXT':r'(?:failed to solve|failed to compute cache key|no space left on device)',
 'DOCKER_PERMISSION':r'(?:permission denied|operation not permitted)',
 'DOCKER_OUT_OF_MEMORY':r'(?:out of memory|signal: killed|exit code: 137)'
}
matches=[name for name,pattern in categories.items() if re.search(pattern,raw,re.I)]
print('BUILD_DIAGNOSIS=COMPLETE')
for name in categories:
 print('BUILD_CLASS_'+name+'='+('yes' if name in matches else 'no'))
# Exit code is not inherently a stacktrace or source disclosure.
codes=re.findall(r'exit code: ([0-9]{1,3})',raw)
print('BUILD_LAST_EXIT_CODE='+(codes[-1] if codes else 'unknown'))
print('NO_BOOKINGS_EXECUTED=yes')
print('NO_DEPLOYMENT_EXECUTED=yes')
print('NO_PRIVATE_SOURCE_UPLOADED=yes')
