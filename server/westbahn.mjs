import {readFileSync,writeFileSync,renameSync,mkdirSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {RULES,planDates,viennaClock,chooseSeat,validateQuote,confirmedReceipt} from '../src/core/westbahn.js';
import {DEFAULT_RESERVATION_PLAN,createReservationPlanStore,isLegacyReservationPlan,nextReservationBatch,reservationWindowOpen} from './reservation-plan.mjs';
import {createCheckoutIntent,chooseVerifiedSeat,verifyDynamicQuote,verifyDynamicReadback,checkoutAttemptKey,dynamicCheckoutReadiness} from './dynamic-checkout.mjs';
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
// Only an explicitly installed server adapter may enable a customized itinerary.
// A read-only account view with incomplete pagination cannot meet this contract.
export function dynamicAdapterReady(adapter){
 const c=adapter?.capabilities;
 return !!c&&c.dynamicItineraries===true&&c.authenticatedFullInventory===true&&
  c.freshZeroEuroQuotes===true&&c.checkoutDomAudit===true&&
  c.durableIdempotency===true&&c.independentAccountReadback===true&&
  ['existing','search','quote','audit','book'].every(k=>typeof adapter[k]==='function');
}
export function createWestbahn({adapter=null,file=null,now=()=>new Date(),gmailConfirm=null,getPlan=null}={}){
 let state=empty(), running=false;
 if(file){try{state=JSON.parse(readFileSync(file,'utf8'));if(!state.rows||typeof state.enabled!=='boolean')throw new Error('Invalid ledger');}catch(e){if(e.code!=='ENOENT')throw e;}}
 const save=()=>{if(file){mkdirSync(dirname(file),{recursive:true,mode:0o700});writeFileSync(file+'.tmp',JSON.stringify(state),{mode:0o600});renameSync(file+'.tmp',file);}};
 // An interrupted checkout is never retried automatically.
 for(const row of Object.values(state.rows)) if(row.status==='booking') {row.status='uncertain';row.detail='Buchung unterbrochen: zuerst beim Anbieter abgleichen.';}
 save();
 const currentPlan=()=>getPlan?getPlan():DEFAULT_RESERVATION_PLAN;
 const status=()=>({providerConnected:!!adapter,dynamicProviderVerified:dynamicAdapterReady(adapter),automatic:state.enabled,running,lastRun:state.lastRun,lastSchedule:state.lastSchedule,rules:RULES,planCompatible:isLegacyReservationPlan(currentPlan()),rows:Object.values(state.rows).sort((a,b)=>a.date.localeCompare(b.date)),planned:nextReservationBatch(currentPlan(),{at:now()}),confirmedThrough:Object.values(state.rows).filter(x=>x.status==='confirmed').map(x=>x.date).sort().at(-1)||null});
 const setEnabled=enabled=>{if(enabled&&!adapter)throw new Error('Kein verifizierter WESTbahn-Buchungsadapter verbunden.');if(enabled&&!isLegacyReservationPlan(currentPlan())&&!dynamicAdapterReady(adapter))throw new Error('Individueller Fahrplan benötigt einen verifizierten Buchungsadapter mit vollständigem dynamischem Checkout.');state.enabled=!!enabled;save();return status();};
 const record=(date,status,detail,extra={})=>{state.rows[date]={date,status,detail,updatedAt:now().toISOString(),...extra};save();};
 const recordUserReported=(travelDate,seat)=>{
  if(typeof travelDate!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(travelDate)||Number.isNaN(Date.parse(travelDate+'T00:00:00Z'))||new Date(travelDate+'T00:00:00Z').toISOString().slice(0,10)!==travelDate)throw new Error('Reisedatum ungültig.');
  if(typeof seat!=='string'||!(/^[0-9]{3}[A-D]$/.test(seat)))throw new Error('Sitzplatz ungültig.');
  const previous=state.rows[travelDate];
  if(previous&&['booking','confirmed','uncertain'].includes(previous.status))throw new Error('Buchungsstatus bereits geschützt. Keine Änderung ohne Abgleich.');
  if(previous?.status==='existing_verified'){
   if(previous.seat!==seat)throw new Error('Bereits verifiziertes Ticket hat anderen Sitzplatz. Keine Änderung.');
   return status();
  }
  if(previous?.status==='user_reported'){
   if(previous.seat!==seat)throw new Error('Bereits gemeldete Buchung hat anderen Sitzplatz. Manuell prüfen.');
   return status();
  }
  record(travelDate,'user_reported','Bestehende Reservierung vom Nutzer angegeben; nicht extern verifiziert. Nicht automatisch erneut buchen.',{seat});
  return status();
 };

 // This may only be called after a positive, authenticated, read-only
 // ticket detail audit. It does NOT confirm a newly submitted checkout.
 const recordVerifiedExisting=(travelDate,seat)=>{
  if(typeof travelDate!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(travelDate)||
     Number.isNaN(Date.parse(travelDate+'T00:00:00Z'))||
     new Date(travelDate+'T00:00:00Z').toISOString().slice(0,10)!==travelDate)
    throw new Error('Reisedatum ungültig.');
  if(typeof seat!=='string'||!(/^[0-9]{3}[A-D]$/.test(seat)))
    throw new Error('Sitzplatz ungültig.');
  const previous=state.rows[travelDate];
  if(previous?.seat&&previous.seat!==seat)
    throw new Error('Widersprüchliche Sitzplätze. Keine automatische Änderung.');
  if(previous&&['confirmed','booking','uncertain'].includes(previous.status))
    return status(); // never weaken or overwrite a checkout-related lock
  if(previous?.status==='existing_verified')
    return status();
  record(travelDate,'existing_verified',
   'Vorhandenes Ticket im Anbieter-Konto mit Datum und Sitzplatz gelesen. Keine neue Buchung.',
   {seat});
  return status();
 };


 // A positive official Gmail receipt can protect a date even if account
 // pagination is incomplete. A missing email NEVER proves no reservation.
 // Do not replace an existing conflicting seat or an unknown order outcome.
 const recordVerifiedEmail=(travelDate,seat)=>{
  if(typeof travelDate!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(travelDate)||
     Number.isNaN(Date.parse(travelDate+'T00:00:00Z'))||
     new Date(travelDate+'T00:00:00Z').toISOString().slice(0,10)!==travelDate)
   throw Error('Ungültiges E-Mail-Reisedatum.');
  if(typeof seat!=='string'||!/^[0-9]{3}[A-D]$/.test(seat))
   throw Error('Ungültiger E-Mail-Sitzplatz.');
  const previous=state.rows[travelDate];
  if(previous?.seat&&previous.seat!==seat)
   throw Error('Abweichender Sitzplatz; keine automatische Überschreibung.');
  if(previous?.status==='confirmed'&&previous.confirmationSource!=='official_email')
   return status();
  if(previous?.status==='confirmed'&&previous.seat===seat)return status();
  record(travelDate,'confirmed','Offizielle WESTbahn-Ticket-E-Mail mit Datum, Zug und Sitzplatz geprüft. Keine neue Buchung.',{
    seat,confirmationSource:'official_email'});
  return status();
 };

 async function run(){
  if(!adapter)throw new Error('Kein WESTbahn-Buchungsadapter verbunden.');if(running)throw new Error('Buchungslauf läuft bereits.');running=true;
  state.lastRun={startedAt:now().toISOString(),status:'running'};save();
  try{
   // All selected travel dates are computed from the same durable app plan.
   // Legacy provider checkout remains restricted to its verified itinerary.
   const dynamic=!isLegacyReservationPlan(currentPlan());
   if(dynamic&&!dynamicAdapterReady(adapter)){
    state.lastRun={...state.lastRun,status:'blocked_unverified_custom_itinerary',finishedAt:now().toISOString()};
    return status();
   }
   const protectedDates=Object.values(state.rows)
    .filter(row=>['confirmed','uncertain','booking','user_reported','existing_verified'].includes(row.status))
    .map(row=>row.date);
   const upcoming=nextReservationBatch(currentPlan(),{at:now(),excludedDates:protectedDates});
   if(!upcoming.length){
    state.lastRun={...state.lastRun,status:'no_planned_dates',finishedAt:now().toISOString()};
    return status();
   }
   // An unreadable inbox is never proof that the passenger has no ticket.
   // Reconcile positively confirmed official emails before any provider writes.
   if(gmailConfirm&&!dynamic){
    let email;
    try{email=await gmailConfirm(upcoming);}
    catch{email=null;}
    if(email?.status!=='email_week_checked'||email.bookingAuthorized!==false||
       !Array.isArray(email.confirmed)||email.confirmed.length>5||
       !Array.isArray(email.conflictingDates)||email.conflictingDates.length>0){
     state.lastRun={...state.lastRun,status:'blocked_email_unavailable',
                    finishedAt:now().toISOString()};
     return status();
    }
    const observed=new Set();
    for(const ticket of email.confirmed){
     if(!ticket||!upcoming.includes(ticket.date)||
        !/^[0-9]{3}[A-D]$/.test(ticket.seat)||
        ticket.source!=='official_email'||observed.has(ticket.date)){
      state.lastRun={...state.lastRun,status:'blocked_email_unavailable',
                     finishedAt:now().toISOString()};
      return status();
     }
     observed.add(ticket.date);
    }
    for(const ticket of email.confirmed){
     try{recordVerifiedEmail(ticket.date,ticket.seat);}
     catch{
      state.lastRun={...state.lastRun,status:'blocked_email_conflict',
                     finishedAt:now().toISOString()};
      return status();
     }
    }
   }
   // Only the five next commuting dates may be considered per run. A six-month
   // preview must never translate into hundreds of unattended checkouts.
   for(const date of upcoming){
    const existing=state.rows[date]; if(existing&&['confirmed','uncertain','booking','user_reported','existing_verified'].includes(existing.status))continue;
    try{
     if(dynamic){
      const plan=currentPlan();
      const details={date,origin:plan.origin,destination:plan.destination,
        departure:plan.departure,class:RULES.class,ticket:RULES.ticket,
        productType:RULES.productType,quantity:1};
      // Any missing or paginated provider inventory blocks checkout.
      const before=await adapter.existing(details);
      if(before?.status==='confirmed'){
       if(before?.accountVerified===true&&before?.inventoryComplete===true&&
          before?.receiptSource==='provider_account'&&
          before.receipt?.date===date&&before.receipt?.origin===plan.origin&&
          before.receipt?.destination===plan.destination&&
          before.receipt?.departure===plan.departure&&
          before.receipt?.class===RULES.class&&
          before.receipt?.ticket===RULES.ticket&&
          before.receipt?.productType===RULES.productType&&
          before.receipt?.quantity===1&&
          before.receipt?.currency==='EUR'&&
          before.receipt?.totalCents===0&&
          /^[0-9]{3}[A-D]$/.test(before.receipt?.seat||'')&&
          typeof before.receipt?.bookingId==='string'&&
          before.receipt.bookingId.trim()&&before.receipt?.confirmed===true){
        record(date,'existing_verified','Vorhandenes Ticket im Anbieter-Konto bestätigt; keine neue Bestellung.',
          {seat:before.receipt.seat,bookingId:before.receipt.bookingId});
       }else record(date,'uncertain','Positives Anbietersignal für ein vorhandenes Ticket, aber Angaben widersprüchlich: keine weitere Buchung ohne manuellen Kontenabgleich.');
       continue;
      }
      if(before?.status!=='none'||before.accountVerified!==true||
         before.inventoryComplete!==true){
       record(date,'blocked','Kein vollständiger, authentifizierter Kontobestand. Keine Buchung.');
       continue;
      }
      const found=await adapter.search(details);
      let intent;
      try{intent=createCheckoutIntent({plan,date,connection:found,at:now()});}
      catch{record(date,'blocked','Anbieterverbindung stimmt nicht vollständig mit dem Fahrplan überein.');continue;}
      const seat=chooseVerifiedSeat(intent,found?.seats);
      if(!seat){record(date,'unavailable','Kein zulässiger Einzelplatz bestätigt.');continue;}
      const quote=await adapter.quote({...intent,seat});
      if(!verifyDynamicQuote(intent,seat,quote,{at:now()})){
       record(date,'blocked','Kein frisches, eindeutig bestätigtes 0-Euro-Angebot.');continue;
      }
      // The adapter must audit the actual WESTbahn checkout DOM *after*
      // selecting the seat. An earlier pricing preview is insufficient.
      const cartAudit=await adapter.audit({intent,seat,quote});
      const preflight=dynamicCheckoutReadiness({intent,seat,quote,cartAudit,
        existing:before,at:now()});
      if(!preflight.allPreflightChecksPassed){
       record(date,'blocked','Live-Warenkorb nicht vollständig und exakt geprüft.');continue;
      }
      // Persist BEFORE any provider side effect. Never retry uncertain outcomes.
      const key=checkoutAttemptKey(intent);
      record(date,'booking','Verifizierter dynamischer Checkout gestartet',
        {seat,key});
      let receipt;
      try{receipt=await adapter.book({intent,seat,quoteId:quote.quoteId,
        idempotencyKey:key,maxTotalCents:0});}
      catch{record(date,'uncertain','Checkout-Ergebnis unklar. Keine automatische Wiederholung.',
        {seat,key});continue;}
      let account;
      try{account=await adapter.existing(details);}
      catch{record(date,'uncertain','Bestellung gesendet, Anbieter-Konto nicht lesbar.',{seat,key});continue;}
      if(!verifyDynamicReadback(intent,seat,receipt,account)){
       record(date,'uncertain','Bestellung gesendet; identischer Anbieter-Kontobeleg fehlt.',{seat,key});
       continue;
      }
      record(date,'confirmed','Bestellung im vollständigen Anbieter-Konto bestätigt.',
        {seat,bookingId:receipt.bookingId});
      continue;
     }
     const before=await adapter.existing({date,...RULES});
     if(before?.status==='confirmed'){
      const receipt=before.receipt;
      // A previously purchased seat is not available for a new selection.
      // Its availability must not invalidate an authenticated existing ticket.
      if(verifiedAccountReadback(before,date,receipt?.seat,receipt?.bookingId))
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
 async function tick(){const c=viennaClock(now());if(!state.enabled||!adapter||running||c.weekday!=='Mon'||!reservationWindowOpen(currentPlan(),now())||state.lastSchedule===c.date)return false;state.lastSchedule=c.date;save();await run();return true;}
 return {status,setEnabled,run,tick,recordUserReported,recordVerifiedExisting,recordVerifiedEmail};
}
// Custom integration must be installed server-side and implement an authorized provider API.
// No browser automation or live provider is fabricated here.
export async function loadWestbahn(env=process.env,sharedPlanStore=null){let adapter=null;if(env.WESTBAHN_ADAPTER_MODULE){const mod=await import(pathToFileURL(resolve(env.WESTBAHN_ADAPTER_MODULE)).href);adapter=await mod.createAdapter();for(const k of ['existing','search','quote','book'])if(typeof adapter?.[k]!=='function')throw new Error('Unvollständiger WESTbahn-Adapter: '+k);}
 const gmailConfirm=env.WESTBAHN_GMAIL_CONFIRMATION_ENABLED==='1'
  ?(await import('./gmail-confirmation.mjs')).createWeeklyGmailConfirmation({env}):null;
 const planStore=sharedPlanStore||createReservationPlanStore({file:env.WESTBAHN_PLAN_STATE||'./data/westbahn-plan.json'});
 return createWestbahn({adapter,gmailConfirm,getPlan:()=>planStore.get(),file:env.WESTBAHN_LEDGER||'./data/westbahn.json'});}
