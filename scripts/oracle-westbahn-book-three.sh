#!/usr/bin/env bash
# Authorized one-shot booking request, strictly three dates, no other days.
# A verified date-specific Tickets no-match and Gmail no-match may permit an exact-zero quote.
# Missing live credentials, adapter, incomplete checks, and ambiguous receipts still block.
set -Eeuo pipefail
[[ "${1:-}" == "--booking-three" ]] || { echo 'THREE_BOOKINGS=BLOCKED_MODE'; exit 64; }
cd /opt/agentzentrale
cid="$(docker compose -f compose.yaml ps -q agentzentrale)"
[[ -n "$cid" ]] || { echo 'THREE_BOOKINGS=BLOCKED_CONTAINER'; exit 3; }
docker exec -i "$cid" node - <<'JS'
const fs=require('node:fs');
(async()=>{
 const e=process.env;
 const ledger=e.WESTBAHN_LEDGER||'/app/server/data/westbahn.json';
 const dates=['2026-11-25','2026-11-26','2026-11-27'];
 const read=()=>JSON.parse(fs.readFileSync(ledger,'utf8'));
 const before=read();
 if(e.WESTBAHN_LIVE_CHECKOUT_ENABLED!=='true'||!e.WESTBAHN_ADAPTER_MODULE||
    !fs.existsSync(e.WESTBAHN_ADAPTER_MODULE)||
    !((e.GMAIL_AUDIT_MODULE&&fs.existsSync(e.GMAIL_AUDIT_MODULE)) ||
      (e.GMAIL_CLIENT_ID&&e.GMAIL_CLIENT_SECRET&&e.GMAIL_REFRESH_TOKEN))||
    !e.AGENTZENTRALE_ACCESS_TOKEN){
   console.log('THREE_BOOKINGS=BLOCKED_PREREQUISITES');process.exitCode=3;return;
 }
 if(before.lastRun?.status==='running'||dates.some(d=>['booking','uncertain','user_reported'].includes(before.rows?.[d]?.status))){
   console.log('THREE_BOOKINGS=BLOCKED_LEDGER');process.exitCode=3;return;
 }
 // Avoid double-starting after a previous successful submission.
 if(dates.every(d=>['confirmed','existing_verified'].includes(before.rows?.[d]?.status))){
   console.log('THREE_BOOKINGS=ALREADY_PROTECTED');return;
 }
 const start=Date.now();
 let response;
 try{
   response=await fetch('http://127.0.0.1:8787/westbahn/run',{
     method:'POST',headers:{'Authorization':'Bearer '+e.AGENTZENTRALE_ACCESS_TOKEN,
       'Content-Type':'application/json'},
     body:JSON.stringify({confirm:'NUR-0-EURO',dates}),
     signal:AbortSignal.timeout(12000)});
 }catch{console.log('THREE_BOOKINGS=BLOCKED_REQUEST_UNKNOWN');process.exitCode=3;return;}
 if(response.status!==202){
   console.log('THREE_BOOKINGS=BLOCKED_API_REJECTED');process.exitCode=3;return;
 }
 console.log('THREE_BOOKINGS=REQUEST_ACCEPTED');
 let done=false;
 for(let i=0;i<180;i++){
   await new Promise(resolve=>setTimeout(resolve,2000));
   let data;
   try{data=read();}catch{continue;}
   const last=data.lastRun||{};
   if(last.status==='finished'&&Date.parse(last.startedAt||0)>=start-5000){done=true;break;}
   if(last.status==='failed'&&Date.parse(last.startedAt||0)>=start-5000){break;}
 }
 if(!done){console.log('THREE_BOOKINGS=OUTCOME_UNCERTAIN');process.exitCode=3;return;}
 const after=read();
 const safe=['confirmed','existing_verified','blocked','unavailable','uncertain'];
 for(const date of dates){
   const status=after.rows?.[date]?.status||'missing';
   console.log('BOOKING_'+date.replaceAll('-','_')+'='+(safe.includes(status)?status:'unknown'));
 }
 console.log('THREE_BOOKINGS=COMPLETED_CHECK_LEDGER');
})().catch(()=>{console.log('THREE_BOOKINGS=BLOCKED_RUNTIME_ERROR');process.exitCode=3});
JS
