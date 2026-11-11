import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {planDates} from '../src/core/westbahn.js';

const script=resolve(dirname(fileURLToPath(import.meta.url)),'browser/worker.py');
const ALLOWED=new Set(['probe','prepare','booking-check','ticket-detail-check']);
const CHECK=new Set(['booking-check','ticket-detail-check']);
const SEAT=/^[0-9]{3}[A-D]$/;

// Only safe, fixed-shape evidence goes back to the AgentZentrale API.
// Never return provider HTML, ticket URLs, customer data or booking codes.
export function sanitizeTicketAudit(raw,mode,date,seat=null){
 const base={date,seat:seat||null,inventoryComplete:false,safeToBook:false,
             bookingAuthorized:false,confirmationVerified:false};
 if(!raw||typeof raw!=='object'||Array.isArray(raw)){
  return {...base,status:'review_required',reason:'invalid_provider_response'};
 }
 if(mode==='ticket-detail-check'){
  const checks={
   detailRead:raw.detailStatus==='detail_read',
   yearVerified:raw.yearVerified===true,
   seatMatched:raw.seatMatched===true,
   tripMatched:raw.tripMatched===true,
   referenceVisible:raw.referenceVisible===true,
   dateExplicit:raw.dateExplicit===true
  };
  const verified=raw.status==='ticket_detail_check'&&
       Object.values(checks).every(x=>x===true) &&
       raw.date===date&&raw.seat===seat&&raw.inventoryComplete===false&&
       raw.safeToBook===false&&raw.bookingAuthorized===false&&
       raw.confirmationVerified===false;
  return {...base,status:verified?'existing_ticket_verified':'review_required',
          checks,reason:verified?'ticket_details_match':'ticket_details_unverified'};
 }
 if(mode==='booking-check'){
  // Positive card observations can prevent a duplicate, but an absent card
  // never proves absence. Pagination is explicitly incomplete.
  const matches=Array.isArray(raw.matches)?raw.matches:[];
  const found=raw.status==='existing_ticket_visible'&&
      raw.inventoryComplete===false&&matches.some(x=>
       x&&typeof x==='object'&&typeof x.seat==='string'&&
       SEAT.test(x.seat)&&x.expectedSeat===true);
  return {...base,status:found?'existing_ticket_visible':'review_required',
          checks:{matchingCardVisible:found},
          reason:found?'positive_account_card':'inventory_not_proven_complete'};
 }
 throw new Error('Unsupported read-only audit.');
}

export function createBrowser({env=process.env,execute=spawn,now=()=>new Date()}={}){
 let busy=false;
 const enabled=env.WESTBAHN_BROWSER_ENABLED==='true';
 const profile=resolve(env.WESTBAHN_BROWSER_PROFILE||'./data/westbahn-browser');
 const status=()=>({enabled,busy,profilePresent:existsSync(resolve(profile,'chromium')),
                     liveBooking:false,mode:'read-only-ticket-audit'});
 async function run(mode,date,seat){
  if(!enabled)throw new Error('Browser auf dem Server noch nicht aktiviert.');
  if(busy)throw new Error('Browser ist bereits in Benutzung.');
  if(!ALLOWED.has(mode))throw new Error('Nicht erlaubter Browserbefehl.');
  if(mode!=='probe'&&(!/^\d{4}-\d{2}-\d{2}$/.test(date||'')||
       !planDates(now()).includes(date)))throw new Error('Reisedatum nicht im erlaubten Pendelplan.');
  if(mode==='ticket-detail-check' && (typeof seat!=='string'||!SEAT.test(seat)))
    throw new Error('Sitzplatz ungültig.');
  if(mode==='booking-check' && seat!==undefined && seat!==null &&
      (typeof seat!=='string'||!SEAT.test(seat)))throw new Error('Sitzplatz ungültig.');
  busy=true;
  try{return await new Promise((done,fail)=>{
   let out='',settled=false;
   const args=[script,mode,
    ...(mode==='probe'?[]:['--date',date]),
    ...((CHECK.has(mode)&&seat)?['--seat',seat]:[])];
   let child;
   try {child=execute(env.WESTBAHN_PYTHON||'python3',args,{
       env:{...env,WESTBAHN_BROWSER_PROFILE:profile},stdio:['ignore','pipe','ignore']
   });}catch{fail(new Error('Browserprozess konnte nicht gestartet werden.'));return;}
   const finish=(error,value)=>{
    if(settled)return;settled=true;clearTimeout(timer);error?fail(error):done(value);
   };
   const timer=setTimeout(()=>{
      child.kill('SIGKILL');
      finish(new Error('Browser-Zeitlimit erreicht. Keine Buchung.'));
   },CHECK.has(mode)?160_000:65_000);
   child.stdout.on('data',chunk=>{
    out+=chunk.toString('utf8');
    if(out.length>16_384){
      child.kill('SIGKILL');
      finish(new Error('Browserantwort zu groß. Keine Buchung.'));
    }
   });
   child.on('error',()=>finish(new Error('Playwright-Browser konnte nicht gestartet werden.')));
   child.on('close',code=>{
    if(code!==0){finish(new Error('Browserprüfung fehlgeschlagen. Keine Buchung.'));return;}
    let raw;try{raw=JSON.parse(out);}catch{
      finish(new Error('Browser lieferte keine gültige Antwort.'));return;
    }
    if(CHECK.has(mode)){
      try{finish(null,sanitizeTicketAudit(raw,mode,date,seat));}
      catch{finish(new Error('Ticketprüfung konnte nicht sicher ausgewertet werden.'));}
      return;
    }
    if(!['reachable','blocked','search_submitted','connection_found'].includes(raw?.status)){
      finish(new Error('Browser lieferte kein eindeutiges Ergebnis.'));return;
    }
    finish(null,raw);
   });
  });}finally{busy=false;}
 }
 return {status,run};
}
