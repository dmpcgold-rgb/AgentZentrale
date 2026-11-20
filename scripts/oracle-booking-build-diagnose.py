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
# Docker BuildKit prefixes test output with '#17 2.3'; locate TAP ordinals
# within those prefixed lines. Report numbers only, never test names.
lines=raw.splitlines()
failed=[]
for line in lines:
 match=re.search(r'(?:^|\\s)not ok\\s+([0-9]{1,3})(?:\\s|$)',line)
 if match: failed.append(int(match.group(1)))
print('BUILD_FIRST_FAILED_TEST_INDEX='+str(failed[0] if failed else 0))
print('BUILD_FAILED_TEST_COUNT='+str(min(len(failed),100)))
print('BUILD_MODULE_SYNTAX_ERROR='+('yes' if bool(re.search(r'SyntaxError:',raw)) else 'no'))
# Identify only known public Dockerfile steps, not arbitrary filenames.
stages={
 'NODE_PUBLIC_TESTS':r'RUN node --test server/tests/',
 'PYTHON_BROWSER_TESTS':r'RUN cd /app/server/browser &&',
 'PYTHON_COMPILATION':r'RUN /opt/agent-venv/bin/python -m compileall',
 'NPM_OR_NODE_SETUP':r'FROM node:22-bookworm-slim',
}
for label,pattern in stages.items():
 print('BUILD_STAGE_'+label+'='+('yes' if bool(re.search(pattern,raw)) else 'no'))
# Never print private test titles; report only whether expected public test
# failures were detected, for accurate guided repairs.
print('BUILD_TAP_FAILURES_FOUND='+('yes' if failed else 'no'))
# Exact diagnosis categories extracted from Node errors, without printing any
# source lines or error strings. A missing named export is a SyntaxError even
# when every source file parses correctly.
kinds={
 'MISSING_NAMED_EXPORT':r'does not provide an export named',
 'UNEXPECTED_TOKEN':r'SyntaxError: Unexpected token',
 'UNEXPECTED_IDENTIFIER':r'SyntaxError: Unexpected identifier',
 'INVALID_REGEXP':r'SyntaxError: Invalid regular expression',
 'MODULE_MISSING':r'ERR_MODULE_NOT_FOUND|Cannot find module',
 'JS_ASSERTION':r'ERR_ASSERTION|AssertionError',
 'JS_REFERENCE_ERROR':r'ReferenceError:',
 'JS_TYPE_ERROR':r'TypeError:',
}
for label,pattern in kinds.items():
 print('BUILD_NODE_ERROR_'+label+'='+('yes' if bool(re.search(pattern,raw,re.I)) else 'no'))
# Restrict attribution to known, public JavaScript modules only.
known=['server/index.mjs','server/westbahn.mjs','server/gmail-audit.mjs',
 'src/core/westbahn.js','server/tests/westbahn.test.mjs',
 'server/tests/gmail-audit.test.mjs','server/booking-readiness.mjs',
 'server/trip-preview.mjs','server/weekly-review.mjs']
for filename in known:
 safe=filename.replace('/','_').replace('.','_').upper()
 print('BUILD_NODE_PUBLIC_'+safe+'='+('yes' if filename in raw else 'no'))

print('NO_BOOKINGS_EXECUTED=yes')
print('NO_DEPLOYMENT_EXECUTED=yes')
print('NO_PRIVATE_SOURCE_UPLOADED=yes')
