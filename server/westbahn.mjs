import {readFileSync,writeFileSync,renameSync,mkdirSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {RULES,planDates,viennaClock,chooseSeat,validateQuote,confirmedReceipt} from '../src/core/westbahn.js';
// A newly booked ticket is only confirmed after a separate read from the
// authenticated provider account, matching the submitted order's reference.
// An adapter claiming success without this readback must never enable retries.
export function verifiedAccountReadback(snapshot, date, seat, bookingId){
 return snapshot?.status==='confirmed' &&
        snapshot.accountVerified===true &&
        snapshot.receiptSource==='provider_account' &&
        snapshot.inventoryComplete===true &&
        confirmedReceipt(snapshot.receipt,date,seat) &&
        typeof bookingId==='string' && bookingId.trim().length>0 &&
        snapshot.receipt.bookingId===bookingId;
}
const empty=()=>({enabled:false,rows:{},lastSchedule:null,lastRun:null});
export function createWestbahn({adapter=null,file=null,now=()=>new Date()}={}){
 let state=empty(), running=false;
 if(file){try{state=JSON.parse(readFileSync(file,'utf8'));if(!state.rows||typeof state.enabled!=='boolean')throw new Error('Invalid ledger');}catch(e){if(e.code!=='ENOENT')throw e;}}
 const save=()=>{if(file){mkdirSync(dirname(file),{recursive:true,mode:0o700});writeFileSync(file+'.tmp',JSON.stringify(state),{mode:0o600});renameSync(file+'.tmp',file);}};
 // An interrupted checkout is never retried automatically.
 for(const row of Object.values(state.rows)) if(row.status==='booking') {row.status='uncertain';row.detail='Buchung unterbrochen: zuerst beim Anbieter abgleichen.';}
 save();
 const status=()=>({providerConnected:!!adapter,automatic:state.enabled,running,lastRun:state.lastRun,lastSchedule:state.lastSchedule,rules:RULES,rows:Object.values(state.rows).sort((a,b)=>a.date.localeCompare(b.date)),planned:planDates(now()),confirmedThrough:Object.values(state.rows).filter(x=>x.status==='confirmed').map(x=>x.date).sort().at(-1)||null});
 const setEnabled=enabled=>{if(enabled&&!adapter)throw new Error('Kein verifizierter WESTbahn-Buchungsadapter verbunden.');state.enabled=!!enabled;save();return status();};
 const record=(date,status,detail,extra={})=>{state.rows[date]={date,status,detail,updatedAt:now().toISOString(),...extra};save();};
 const recordUserReported=(travelDate,seat)=>{
  if(typeof travelDate!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(travelDate)||Number.isNaN(Date.parse(travelDate+'T00:00:00Z'))||new Date(travelDate+'T00:00:00Z').toISOString().slice(0,10)!==travelDate)throw new Error('Reisedatum ungültig.');
  if(typeof seat!=='string'||!(/^[0-9]{3}[A-D]$/.test(seat)))throw new Error('Sitzplatz ungültig.');
  const previous=state.rows[travelDate];
  if(previous&&['booking','confirmed','uncertain'].includes(previous.status))throw new Error('Buchungsstatus bereits geschützt. Keine Änderung ohne Abgleich.');
  if(previous?.status==='user_reported'){
   if(previous.seat!==seat)throw new Error('Bereits gemeldete Buchung hat anderen Sitzplatz. Manuell prüfen.');
   return status();
  }
  record(travelDate,'user_reported','Bestehende Reservierung vom Nutzer angegeben; nicht extern verifiziert. Nicht automatisch erneut buchen.',{seat});
  return status();
 };

 async function run(){
  if(!adapter)throw new Error('Kein WESTbahn-Buchungsadapter verbunden.');if(running)throw new Error('Buchungslauf läuft bereits.');running=true;
  state.lastRun={startedAt:now().toISOString(),status:'running'};save();
  try{
   for(const date of planDates(now())){
    const existing=state.rows[date]; if(existing&&['confirmed','uncertain','booking','user_reported'].includes(existing.status))continue;
    try{
     const before=await adapter.existing({date,...RULES});
     if(before?.status==='confirmed'){
      const receipt=before.receipt;
      if(verifiedAccountReadback(before,date,receipt?.seat,receipt?.bookingId)&&
          chooseSeat([before.seat])?.id===receipt.seat)
        record(date,'confirmed','Bereits beim Anbieter reserviert.',{seat:receipt.seat,bookingId:receipt.bookingId});
      else
        record(date,'blocked','Vorhandene Buchung ist nicht eindeutig passend; keine Doppelbuchung.');
      continue;
     }
     // The provider must prove that all relevant existing bookings were
     // checked, otherwise a "none" response cannot authorize a checkout.
     if(before?.status!=='none'||before.accountVerified!==true||before.inventoryComplete!==true){
       record(date,'blocked','Buchungsbestand nicht vollständig und authentifiziert geprüft; keine Buchung.');
       continue;
     }
     const found=await adapter.search({date,...RULES});
     if(!found||found.status!=='available'){record(date,'unavailable','Verbindung nicht verfügbar oder nicht bestätigt.');continue;}
     if(found.date!==date||found.origin!==RULES.origin||found.destination!==RULES.destination||found.departure!==RULES.departure||found.class!==RULES.class||typeof found.connectionId!=='string'||!found.connectionId){record(date,'blocked','Abweichende Verbindung oder Klasse.');continue;}
     const seat=chooseSeat(found.seats);if(!seat){record(date,'unavailable','Kein geeigneter verfügbarer Einzelplatz.');continue;}
     const quote=await adapter.quote({date,seat:seat.id,connectionId:found.connectionId,...RULES});
     if(!validateQuote(quote,date,seat.id)){record(date,'blocked','Preis oder Buchungsdaten nicht exakt bestätigt; keine Buchung.');continue;}
     // Persist before side effect. The provider must honor this stable idempotency key.
     const key=`agentzentrale-westbahn-${date}-${RULES.departure.replace(':','')}`;
     record(date,'booking','Checkout gestartet',{seat:seat.id,key});
     let receipt;try{receipt=await adapter.book({quoteId:quote.quoteId,idempotencyKey:key,maxTotalCents:0});}catch{record(date,'uncertain','Checkout-Ausgang unklar. Nicht automatisch erneut versuchen.',{seat:seat.id,key});continue;}
     if(!confirmedReceipt(receipt,date,seat.id)){
       record(date,'uncertain','Keine eindeutige Buchungsbestätigung. Manuell prüfen.',{seat:seat.id,key});
       continue;
     }
     // Read the provider account AFTER checkout. A successful HTTP response,
     // a zero-euro cart or a success banner alone is insufficient evidence.
     // A failure here is an UNCERTAIN purchase, never a retryable absence.
     let readback;
     try {readback=await adapter.existing({date,...RULES});}
     catch {record(date,'uncertain','Bestellung gesendet, Kontonachweis nicht erreichbar. Nicht erneut buchen.',{seat:seat.id,key});continue;}
     if(!verifiedAccountReadback(readback,date,seat.id,receipt.bookingId)){
       record(date,'uncertain','Bestellung gesendet, aber kein identischer bestätigter Kontobeleg. Nicht erneut buchen.',{seat:seat.id,key});
       continue;
     }
     record(date,'confirmed','Bestellung und identischer Anbieter-Kontobeleg bestätigt.',{seat:receipt.seat,bookingId:receipt.bookingId});
    }catch{if(state.rows[date]?.status==='booking')record(date,'uncertain','Unklarer Buchungsausgang. Nicht erneut versuchen.');else record(date,'blocked','Anbieterfehler; keine Buchung vorgenommen.');}
   }
   state.lastRun={...state.lastRun,status:'finished',finishedAt:now().toISOString()};
  }catch(e){state.lastRun={...state.lastRun,status:'failed',finishedAt:now().toISOString()};throw e;}finally{running=false;save();}
  return status();
 }
 async function tick(){const c=viennaClock(now());if(!state.enabled||!adapter||running||c.weekday!=='Mon'||c.time<'07:00'||state.lastSchedule===c.date)return false;state.lastSchedule=c.date;save();await run();return true;}
 return {status,setEnabled,run,tick,recordUserReported};
}
// Custom integration must be installed server-side and implement an authorized provider API.
// No browser automation or live provider is fabricated here.
export async function loadWestbahn(env=process.env){let adapter=null;if(env.WESTBAHN_ADAPTER_MODULE){const mod=await import(pathToFileURL(resolve(env.WESTBAHN_ADAPTER_MODULE)).href);adapter=await mod.createAdapter();for(const k of ['existing','search','quote','book'])if(typeof adapter?.[k]!=='function')throw new Error('Unvollständiger WESTbahn-Adapter: '+k);}
 return createWestbahn({adapter,file:env.WESTBAHN_LEDGER||'./data/westbahn.json'});}
