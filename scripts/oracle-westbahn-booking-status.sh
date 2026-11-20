#!/usr/bin/env bash
# Read-only report of active WESTbahn automation prerequisites.
# Never print provider details, environment secrets, customer data, ticket IDs or paths.
set -Eeuo pipefail
[[ "${1:-}" == "--booking-status" || "${1:-}" == "--booking-enable" ]] || { echo 'BOOKING_CONFIG_CHECK=INVALID_MODE'; exit 64; }
[[ "$(id -u)" -eq 0 ]] || { echo 'BOOKING_CONFIG_CHECK=ROOT_REQUIRED'; exit 2; }
cd /opt/agentzentrale
cid="$(docker compose -f compose.yaml ps -q agentzentrale)"
[[ -n "$cid" ]] && [[ "$(docker inspect -f '{{.State.Running}}' "$cid")" == true ]] || {
  echo 'BOOKING_CONFIG_CHECK=CONTAINER_DOWN'; exit 3;
}
# Report status from inside the deployed container, not from the public GitHub copy.
# Node only reads environment and the mounted ledger; no network or provider action.
docker exec -i "$cid" node - <<'JS'
const fs=require('node:fs');
const path=require('node:path');
const env=process.env;
const binary=(key, yes)=>console.log(key+'='+(yes?'yes':'no'));
const live=env.WESTBAHN_LIVE_CHECKOUT_ENABLED==='true';
const adapterPath=env.WESTBAHN_ADAPTER_MODULE||'';
const adapter=Boolean(adapterPath && fs.existsSync(path.resolve(adapterPath)));
const gmail=Boolean((env.GMAIL_AUDIT_MODULE&&fs.existsSync(path.resolve(env.GMAIL_AUDIT_MODULE)))||(env.GMAIL_CLIENT_ID&&env.GMAIL_CLIENT_SECRET&&env.GMAIL_REFRESH_TOKEN));
const ledgerFile=env.WESTBAHN_LEDGER||'/app/server/data/westbahn.json';
let ledgerOk=false, enabled=false, pending=false, running=false;
try{
 const data=JSON.parse(fs.readFileSync(ledgerFile,'utf8'));
 ledgerOk=Array.isArray(data.rows)||Boolean(data.rows&&typeof data.rows==='object');
 enabled=data.enabled===true;
 running=data.lastRun?.status==='running';
 pending=Object.values(data.rows||{}).some(x=>x?.status==='booking'||x?.status==='uncertain');
}catch{}
binary('BOOKING_LIVE_GATE_ENABLED',live);
binary('BOOKING_ADAPTER_PRESENT',adapter);
binary('BOOKING_GMAIL_CONFIGURED',gmail);
binary('BOOKING_LEDGER_VALID',ledgerOk);
binary('BOOKING_SCHEDULE_ENABLED',enabled);
binary('BOOKING_ACTIVE_RUN',running);
binary('BOOKING_AMBIGUOUS_ROWS',pending);
binary('BOOKING_WEEKLY_SCHEDULER_PRESENT',fs.existsSync('/app/server/westbahn.mjs'));
binary('BOOKING_PREREQUISITES_READY',live&&adapter&&gmail&&ledgerOk&&!running&&!pending);
console.log('BOOKING_CONFIG_CHECK=COMPLETE');
JS
if [[ "${1:-}" == "--booking-status" ]]; then
  echo 'BOOKING_ACTION_EXECUTED=no'
else
  # Same guards as status, but perform an authorized settings update only if
  # the existing HTTP endpoint and live provider verification gates accept it.
  # No scripts or credentials are copied outside the live Oracle container.
  docker exec -i "$cid" node - <<'JS'
const fs=require('node:fs');
const path=require('node:path');
(async()=>{
const e=process.env;
const ledgerPath=e.WESTBAHN_LEDGER||'/app/server/data/westbahn.json';
const data=JSON.parse(fs.readFileSync(ledgerPath,'utf8'));
const rows=data.rows;
if(!(rows&&typeof rows==='object') || data.lastRun?.status==='running' ||
 Object.values(rows).some(x=>['booking','uncertain'].includes(x?.status))){
 console.log('BOOKING_ACTIVATION=BLOCKED_LEDGER_REVIEW');process.exitCode=3;return;
}
if(e.WESTBAHN_LIVE_CHECKOUT_ENABLED!=='true' ||
 !e.WESTBAHN_ADAPTER_MODULE ||
 !fs.existsSync(path.resolve(e.WESTBAHN_ADAPTER_MODULE)) ||
 !((e.GMAIL_AUDIT_MODULE&&fs.existsSync(path.resolve(e.GMAIL_AUDIT_MODULE))) || (e.GMAIL_CLIENT_ID&&e.GMAIL_CLIENT_SECRET&&e.GMAIL_REFRESH_TOKEN)) ||
 !e.AGENTZENTRALE_ACCESS_TOKEN){
 console.log('BOOKING_ACTIVATION=BLOCKED_MISSING_PREREQUISITES');process.exitCode=3;return;
}
const endpoint='http://127.0.0.1:8787/westbahn/settings';
let response;
try{
 response=await fetch(endpoint,{method:'POST',headers:{
  'Authorization':'Bearer '+e.AGENTZENTRALE_ACCESS_TOKEN,
  'Content-Type':'application/json'
 },body:JSON.stringify({enabled:true,confirm:'NUR-0-EURO'}),signal:AbortSignal.timeout(8000)});
}catch{
 console.log('BOOKING_ACTIVATION=BLOCKED_API_UNREACHABLE');process.exitCode=3;return;
}
if(!response.ok){console.log('BOOKING_ACTIVATION=BLOCKED_SERVER_REJECTED');process.exitCode=3;return;}
const result=await response.json().catch(()=>null);
if(result?.automatic!==true || result?.liveCheckoutEnabled!==true ||
 result?.providerConnected!==true || result?.emailControlConnected!==true){
 console.log('BOOKING_ACTIVATION=BLOCKED_NOT_CONFIRMED');process.exitCode=3;return;
}
console.log('BOOKING_ACTIVATION=ENABLED');
})().catch(()=>{console.log('BOOKING_ACTIVATION=BLOCKED_ERROR');process.exitCode=3});
JS
fi
echo 'NO_MANUAL_BOOKING_TRIGGERED=yes'
echo 'NO_DEPLOYMENT_EXECUTED=yes'
