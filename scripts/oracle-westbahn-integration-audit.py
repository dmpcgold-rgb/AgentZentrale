#!/usr/bin/env python3
"""Read-only WESTbahn/Gmail compatibility audit; never publish source or credentials."""
import os
import re
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
flags('GMAIL_AUDIT_MODULE_SET',!!e.GMAIL_AUDIT_MODULE);
flags('GMAIL_AUDIT_MODULE_PRESENT',!!e.GMAIL_AUDIT_MODULE&&fs.existsSync(path.resolve(e.GMAIL_AUDIT_MODULE)));
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
"GMAIL_AUDIT_MODULE_SET","GMAIL_AUDIT_MODULE_PRESENT",
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
# Parse the deployed checkout scripts inside the container. Never import them:
# legacy scripts may submit a reservation as soon as they run.
checkout_inventory = r"""
import ast
from pathlib import Path

directory = Path('/app/server/browser')
required = {'existing', 'search', 'quote', 'audit', 'book'}
for day in ('25', '26', '27'):
    script = directory / f'checkout_202611{day}.py'
    tree = None
    try:
        if script.is_file() and script.stat().st_size <= 1024 * 1024:
            tree = ast.parse(script.read_bytes())
    except (OSError, SyntaxError, ValueError):
        pass
    functions = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    } if tree is not None else set()
    print(f'CHECKOUT_{day}_SYNTAX=' + ('yes' if tree is not None else 'no'))
    print(f'CHECKOUT_{day}_NAMED_OPERATIONS=' + ('yes' if required <= functions else 'no'))
"""
try:
    inventory = subprocess.run(
        ["docker", "exec", "-i", container, "python3", "-c", checkout_inventory],
        capture_output=True, text=True, timeout=20, check=True,
    )
except (OSError, subprocess.SubprocessError):
    print("INTEGRATION_AUDIT=BLOCKED_PRIVATE_SCRIPT_INSPECTION")
    raise SystemExit(3)

inventory_allow = {
    f"CHECKOUT_{day}_{check}"
    for day in ("25", "26", "27")
    for check in ("SYNTAX", "NAMED_OPERATIONS")
}
inventory_results = {}
for line in inventory.stdout.splitlines():
    key, separator, value = line.partition("=")
    if separator and key in inventory_allow and value in ("yes", "no"):
        inventory_results[key] = value
if set(inventory_results) != inventory_allow:
    print("INTEGRATION_AUDIT=BLOCKED_UNVERIFIED_INVENTORY")
    raise SystemExit(3)
for key in sorted(inventory_allow):
    print(key + "=" + inventory_results[key])

# Look for the relevant setting names in common project configuration files.
# Never evaluate an env file, resolve its values, or print its contents.
gmail_patterns = {
    "HOST_GMAIL_OAUTH_KEYS_DECLARED": (
        "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN",
    ),
    "HOST_GMAIL_MODULE_KEY_DECLARED": ("GMAIL_AUDIT_MODULE",),
}
declarations = set()
for config in (root / ".env", root / ".env.local", root / "compose.yaml",
               root / "compose.override.yaml"):
    try:
        if not config.is_file() or config.stat().st_size > 1024 * 1024:
            continue
        for line in config.read_text(errors="replace").splitlines():
            match = re.match(r'^\s*(?:-\s+|export\s+)?(GMAIL_[A-Z_]+)\s*(?:=|:|$)', line)
            if match:
                declarations.add(match.group(1))
    except OSError:
        continue
for name, keys in gmail_patterns.items():
    print(name + "=" + ("yes" if set(keys) <= declarations else "no"))

# This is NOT a live API verification and never runs a checkout.
private_dir=Path("/root/agentzentrale-private-snapshots")
print("PRIVATE_SNAPSHOT_ROOT_PRESENT="+("yes" if private_dir.is_dir() else "no"))
print("INTEGRATION_AUDIT=COMPLETE")
print("NO_BOOKINGS_EXECUTED=yes")
print("NO_DEPLOYMENT_EXECUTED=yes")
print("NO_PRIVATE_SOURCE_UPLOADED=yes")
