#!/usr/bin/env bash
# One-off authorized booking attempt for exactly 25–27 November 2026.
# Never print secrets, confirmation links, passenger data or ticket numbers.
set -Eeuo pipefail
[[ "${1:-}" == "--book-target-20261125-27" ]] || { echo 'TARGETED_BOOKING=BLOCKED_MODE'; exit 64; }
[[ "$(id -u)" -eq 0 ]] || { echo 'TARGETED_BOOKING=BLOCKED_USER'; exit 2; }
cd /opt/agentzentrale
cid="$(docker compose ps -q agentzentrale)"
[[ -n "$cid" && "$(docker inspect -f '{{.State.Running}}' "$cid")" == true ]] || {
 echo 'TARGETED_BOOKING=BLOCKED_CONTAINER'; exit 3;
}
docker exec -i "$cid" node - <<'JS'
const days=['2026-11-25','2026-11-26','2026-11-27'];
const bad=['uncertain','booking'];
const e=process.env,base='http://127.0.0.1:8787';
const token=e.AGENTZENTRALE_ACCESS_TOKEN;
const output=(key,value)=>console.log(key+'='+value);
(async()=>{
 if(!token || e.WESTBAHN_LIVE_CHECKOUT_ENABLED!=='true'){
  output('TARGETED_BOOKING','BLOCKED_LIVE_DISABLED');process.exitCode=3;return;
 }
 const headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'};
 async function request(url,options={}){
  const response=await fetch(base+url,{...options,headers,signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw Error('api_rejected');
  return response.json();
 }
 let before;
 try{before=await request('/westbahn/status');}catch{
  output('TARGETED_BOOKING','BLOCKED_STATUS_API');process.exitCode=3;return;
 }
 if(before.liveCheckoutEnabled!==true||before.providerConnected!==true||
   before.emailControlConnected!==true||before.running===true){
  output('TARGETED_BOOKING','BLOCKED_PROVIDER_NOT_READY');process.exitCode=3;return;
 }
 const rows=Object.fromEntries((before.rows||[]).map(x=>[x.date,x]));
 if(days.some(d=>bad.includes(rows[d]?.status))){
  output('TARGETED_BOOKING','BLOCKED_UNCERTAIN_RESERVATION');process.exitCode=3;return;
 }
 if(!days.some(d=>!['confirmed','user_reported','existing_verified'].includes(rows[d]?.status))){
  output('TARGETED_BOOKING','ALREADY_PROTECTED');return;
 }
 // No later dates can be included in this request.
 let result;
 try{
  result=await request('/westbahn/run',{method:'POST',body:JSON.stringify({
   confirm:'NUR-0-EURO',dates:days
  })});
 }catch{
  output('TARGETED_BOOKING','BLOCKED_RUN_NOT_ACCEPTED');process.exitCode=3;return;
 }
 if(result.accepted!==true){
  output('TARGETED_BOOKING','BLOCKED_RUN_NOT_ACCEPTED');process.exitCode=3;return;
 }
 output('TARGETED_BOOKING','RUN_ACCEPTED');
 let done=null;
 for(let attempt=0;attempt<150;attempt++){
  await new Promise(r=>setTimeout(r,4000));
  try{
   const state=await request('/westbahn/status');
   if(state.lastRun?.status==='finished'&&!state.running){done=state;break;}
   if(state.lastRun?.status==='failed'){break;}
  }catch{break;}
 }
 if(!done){
  output('TARGETED_BOOKING','OUTCOME_UNKNOWN_CHECK_LEDGER');
  process.exitCode=4;return;
 }
 const latest=Object.fromEntries((done.rows||[]).map(x=>[x.date,x]));
 const allowed=new Set(['confirmed','existing_verified','user_reported','uncertain','blocked','unavailable']);
 for(const d of days){
  const val=latest[d]?.status||'missing';
  output('BOOKING_'+d.replaceAll('-',''),allowed.has(val)?val.toUpperCase():'UNKNOWN');
 }
 if(days.every(d=>latest[d]?.status==='confirmed' || latest[d]?.status==='existing_verified' || latest[d]?.status==='user_reported')){
  output('TARGETED_BOOKING','ALL_DATES_PROTECTED');
 }else{
  output('TARGETED_BOOKING','INCOMPLETE_REVIEW_REQUIRED');
  process.exitCode=5;
 }
})().catch(()=>{output('TARGETED_BOOKING','BLOCKED_UNEXPECTED_ERROR');process.exitCode=3});
JS
