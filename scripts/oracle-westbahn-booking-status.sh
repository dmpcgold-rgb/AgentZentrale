#!/usr/bin/env bash
# Read-only report of active WESTbahn automation prerequisites.
# Never print provider details, environment secrets, customer data, ticket IDs or paths.
set -Eeuo pipefail
[[ "${1:-}" == "--booking-status" ]] || { echo 'BOOKING_CONFIG_CHECK=INVALID_MODE'; exit 64; }
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
const gmail=Boolean(env.GMAIL_CLIENT_ID&&env.GMAIL_CLIENT_SECRET&&env.GMAIL_REFRESH_TOKEN);
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
echo 'BOOKING_ACTION_EXECUTED=no'
echo 'NO_BOOKINGS_EXECUTED=yes'
echo 'NO_DEPLOYMENT_EXECUTED=yes'
