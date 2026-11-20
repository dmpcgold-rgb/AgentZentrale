#!/usr/bin/env python3
"""Read-only private WESTbahn adapter capability audit; publish no source/credentials."""
import ast
import os
from pathlib import Path
import subprocess
import sys

if sys.argv[1:] != ["--integration-audit"] or os.geteuid() != 0:
    print("INTEGRATION_AUDIT=BLOCKED_INVALID_INVOCATION")
    raise SystemExit(3)
root=Path("/opt/agentzentrale")
if not (root/"compose.yaml").exists():
    print("INTEGRATION_AUDIT=BLOCKED_DEPLOYMENT_MISSING")
    raise SystemExit(3)
try:
    container=subprocess.run(
        ["docker","compose","-f",str(root/"compose.yaml"),"ps","-q","agentzentrale"],
        cwd=root,text=True,capture_output=True,timeout=15,check=True
    ).stdout.strip()
except (OSError,subprocess.SubprocessError):
    container=""
if not container:
    print("INTEGRATION_AUDIT=BLOCKED_CONTAINER_MISSING")
    raise SystemExit(3)
# Never print stdout from Docker container; it may contain sensitive state.
checks=r'''
const fs=require('node:fs');
const path=require('node:path');
const e=process.env;
const flags=(name,value)=>console.log(name+'='+(value?'yes':'no'));
const adapter=e.WESTBAHN_ADAPTER_MODULE||'';
flags('LIVE_GATE_ON',e.WESTBAHN_LIVE_CHECKOUT_ENABLED==='true');
flags('ADAPTER_PATH_SET',!!adapter);
flags('ADAPTER_FILE_PRESENT',!!adapter&&fs.existsSync(path.resolve(adapter)));
flags('GMAIL_OAUTH_CLIENT_SET',!!e.GMAIL_CLIENT_ID);
flags('GMAIL_OAUTH_SECRET_SET',!!e.GMAIL_CLIENT_SECRET);
flags('GMAIL_OAUTH_REFRESH_SET',!!e.GMAIL_REFRESH_TOKEN);
const dir='/app/server/browser';
for(const day of ['25','26','27']){
 flags('PRIVATE_CHECKOUT_'+day+'_PRESENT',fs.existsSync(dir+'/checkout_202611'+day+'.py'));
}
'''
try:
    result=subprocess.run(["docker","exec","-i",container,"node","-e",checks],
                          capture_output=True,text=True,timeout=20,check=True)
except (OSError,subprocess.SubprocessError):
    print("INTEGRATION_AUDIT=BLOCKED_DOCKER_INSPECTION")
    raise SystemExit(3)
allow={
"LIVE_GATE_ON","ADAPTER_PATH_SET","ADAPTER_FILE_PRESENT",
"GMAIL_OAUTH_CLIENT_SET","GMAIL_OAUTH_SECRET_SET","GMAIL_OAUTH_REFRESH_SET",
"PRIVATE_CHECKOUT_25_PRESENT","PRIVATE_CHECKOUT_26_PRESENT",
"PRIVATE_CHECKOUT_27_PRESENT"
}
results={}
for line in result.stdout.splitlines():
    k,sep,v=line.partition("=")
    if sep and k in allow and v in ("yes","no"):
        results[k]=v
if set(results)!=allow:
    print("INTEGRATION_AUDIT=BLOCKED_UNVERIFIED_OUTPUT")
    raise SystemExit(3)
for key in sorted(allow):
    print(key+"="+results[key])
# Inspect only local private Python AST metadata, no code or names emitted.
# This is NOT a live API verification and never runs a checkout.
private_dir=Path("/root/agentzentrale-private-snapshots")
print("PRIVATE_SNAPSHOT_ROOT_PRESENT="+("yes" if private_dir.is_dir() else "no"))
print("INTEGRATION_AUDIT=COMPLETE")
print("NO_BOOKINGS_EXECUTED=yes")
print("NO_DEPLOYMENT_EXECUTED=yes")
print("NO_PRIVATE_SOURCE_UPLOADED=yes")
