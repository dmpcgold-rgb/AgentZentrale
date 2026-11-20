#!/usr/bin/env bash
# Read-only Gmail configuration discovery on the existing Oracle host.
# Never output credentials, email content, tokens or ticket identifiers.
set -Eeuo pipefail
[[ "${1:-}" == "--gmail-check" ]] || { echo "GMAIL_CHECK=INVALID_MODE"; exit 64; }
[[ "$(id -u)" -eq 0 ]] || { echo "GMAIL_CHECK=ROOT_REQUIRED"; exit 3; }
cd /opt/agentzentrale
cid="$(docker compose -f compose.yaml ps -q agentzentrale)"
[[ -n "$cid" ]] || { echo "GMAIL_CHECK=CONTAINER_MISSING"; exit 3; }
python3 - <<'PY'
from pathlib import Path
root = Path('/opt/agentzentrale')
keys = ('GMAIL_CLIENT_ID', 'GMAIL_CLIENT_SECRET', 'GMAIL_REFRESH_TOKEN', 'GMAIL_AUDIT_MODULE')
declared = set()
nonempty = set()
for file in (root/'server/.env', root/'.env', root/'.env.local'):
    try:
        if not file.is_file() or file.stat().st_size > 1024*1024:
            continue
        for line in file.read_text(errors='replace').splitlines():
            line = line.strip()
            if line.startswith('export '):
                line = line[len('export '):]
            name, sep, value = line.partition('=')
            if sep and name.strip() in keys:
                name = name.strip()
                declared.add(name)
                if value.strip().strip(chr(34)).strip(chr(39)):
                    nonempty.add(name)
    except OSError:
        continue
print('GMAIL_HOST_OAUTH_CONFIG_PRESENT=' + ('yes' if all(x in nonempty for x in keys[:3]) else 'no'))
print('GMAIL_HOST_MODULE_CONFIG_PRESENT=' + ('yes' if keys[3] in nonempty else 'no'))
print('GMAIL_HOST_CONFIG_KEYS_DECLARED=' + ('yes' if declared else 'no'))
PY
docker exec -i "$cid" node --input-type=module - <<'JS'
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
import {createGmailAudit} from '/app/server/gmail-audit.mjs';
const e=process.env;
let gmail;
try {
  if(e.GMAIL_AUDIT_MODULE){
    const mod=await import(pathToFileURL(resolve(e.GMAIL_AUDIT_MODULE)).href);
    if(typeof mod.createGmailAudit!=='function')throw Error('invalid module');
    gmail=await mod.createGmailAudit({env:e});
  }else if(e.GMAIL_CLIENT_ID&&e.GMAIL_CLIENT_SECRET&&e.GMAIL_REFRESH_TOKEN){
    gmail=createGmailAudit({clientId:e.GMAIL_CLIENT_ID,clientSecret:e.GMAIL_CLIENT_SECRET,refreshToken:e.GMAIL_REFRESH_TOKEN});
  }else{
    console.log('GMAIL_CHECK=NOT_CONFIGURED_IN_CONTAINER');
    process.exit(3);
  }
  if(typeof gmail?.inspect!=='function')throw Error('invalid inspect');
  // Read-only real network request; no message body or IDs are logged.
  const res=await gmail.inspect({date:'2026-11-25'});
  if(res?.status==='possible_existing'||res?.status==='no_matching_email_observed'){
    console.log('GMAIL_CHECK=CONNECTED_READ_ONLY');
    console.log('GMAIL_CHECKOUT_NOT_TRIGGERED=yes');
  }else{
    console.log('GMAIL_CHECK=UNVERIFIED_RESPONSE');process.exitCode=3;
  }
}catch{
  console.log('GMAIL_CHECK=ACCESS_FAILED');process.exitCode=3;
}
JS
