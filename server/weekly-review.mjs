import {readFileSync,writeFileSync,renameSync,mkdirSync} from 'node:fs';
import {dirname} from 'node:path';
import {planDates,viennaClock} from '../src/core/westbahn.js';
import {sanitizeBatchInventory} from './browser.mjs';

const SINGLE_SEAT=/^[0-9]{3}[A-D]$/;
const sameIso=d=>typeof d==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(d)&&
  !Number.isNaN(Date.parse(d+'T00:00:00Z'))&&
  new Date(d+'T00:00:00Z').toISOString().slice(0,10)===d;

// Only strictly verified positive read-only ticket evidence can protect a day.
// A missing or ambiguous ticket NEVER establishes an empty provider inventory.
export function applyVerifiedBatch(batch,days,westbahn){
 if(!Array.isArray(days)||days.length<1||days.length>5||
    days.some(d=>!sameIso(d))||new Set(days).size!==days.length)
   throw new Error('Invalid review dates');
 const base={status:'review_required',days:days.map(date=>({
  date,status:'review_required',seats:[],dateVerified:false,
  detailVerified:false,potentialDuplicate:false,safeToBook:false
 })),inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
 ledgerProtectedDates:[],ledgerReviewDates:[]};
 // Validate the *whole* report before changing any persistent booking state.
 const audited=sanitizeBatchInventory(batch,days);
 if(audited.status!=='inventory_batch_read')return base;
 const protectedDates=[],reviewDates=[];
 for(let i=0;i<days.length;i++){
  const item=audited.days[i];
  const proven=item.status==='detail_verified'&&
    item.detailVerified===true&&item.dateVerified===true&&
    item.potentialDuplicate===true&&item.safeToBook===false&&
    Array.isArray(item.seats)&&item.seats.length===1&&SINGLE_SEAT.test(item.seats[0]);
  if(!proven)continue;
  try{
    const ledger=westbahn.recordVerifiedExisting(item.date,item.seats[0]);
    const row=ledger?.rows?.find(x=>x.date===item.date);
    if(row?.seat===item.seats[0]&&
       ['existing_verified','confirmed'].includes(row.status))
      protectedDates.push(item.date);
    else reviewDates.push(item.date);
  }catch{
    reviewDates.push(item.date);
  }
 }
 return {
  status:'inventory_batch_read',days:audited.days,
  accountPageReads:audited.accountPageReads,coverage:audited.coverage,
  inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
  ledgerProtectedDates:protectedDates,ledgerReviewDates:reviewDates
 };
}

// The read-only review runs every Monday at 07:00 Vienna time, without an
// unattended checkout. It stores only dates, statuses and seat codes.
export function createWeeklyReview({browser,westbahn,now=()=>new Date(),
 file=null,enabled=true}={}){
 let running=false;
 let state={lastSchedule:null,lastRun:null,lastSuccessWeek:null,
            attemptsThisWeek:0,nextRetryAt:null};
 if(file){
  try{
   const loaded=JSON.parse(readFileSync(file,'utf8'));
   if(loaded&&typeof loaded==='object'&&
      (loaded.lastSchedule===null||sameIso(loaded.lastSchedule))&&
      (!loaded.lastRun||typeof loaded.lastRun==='object')){
    state={lastSchedule:loaded.lastSchedule,lastRun:loaded.lastRun??null,
      lastSuccessWeek:typeof loaded.lastSuccessWeek==='string'&&sameIso(loaded.lastSuccessWeek)
        ?loaded.lastSuccessWeek
        :loaded.lastSchedule && loaded.lastRun?.status==='inventory_batch_read'
          ?loaded.lastSchedule:null,
      attemptsThisWeek:Number.isInteger(loaded.attemptsThisWeek)&&
       loaded.attemptsThisWeek>=0&&loaded.attemptsThisWeek<=2?loaded.attemptsThisWeek:0,
      nextRetryAt:typeof loaded.nextRetryAt==='string'&&
        !Number.isNaN(Date.parse(loaded.nextRetryAt))?loaded.nextRetryAt:null
    };
   }
  }catch(e){if(e.code!=='ENOENT')throw e;}
 }
 const save=()=>{if(file){
  mkdirSync(dirname(file),{recursive:true,mode:0o700});
  writeFileSync(file+'.tmp',JSON.stringify(state),{mode:0o600});
  renameSync(file+'.tmp',file);
 }};
 const status=()=>({enabled,running,lastSchedule:state.lastSchedule,lastRun:state.lastRun,
  lastSuccessWeek:state.lastSuccessWeek,attemptsThisWeek:state.attemptsThisWeek,
  nextRetryAt:state.nextRetryAt,purchaseEnabled:false,inventoryComplete:false});
 async function run(){
  // A deliberate manual read is allowed even if Monday automation is disabled.
  if(running)throw Error('Sammelprüfung läuft bereits.');
  const days=planDates(now()).slice(0,5);
  if(days.length===0)throw Error('Keine Pendeltage im Prüfzeitraum.');
  running=true;
  const startedAt=now().toISOString();
  try {
    const audit=await browser.run('inventory-batch',null,null,days);
    const result=applyVerifiedBatch(audit,days,westbahn);
    state.lastRun={startedAt,finishedAt:now().toISOString(),status:result.status,
      days:result.days.map(x=>({date:x.date,status:x.status,seats:x.seats})),
      ledgerProtectedDates:result.ledgerProtectedDates,
      ledgerReviewDates:result.ledgerReviewDates,coverage:result.coverage||null,
      inventoryComplete:false,safeToBook:false,bookingAuthorized:false};
    save();
    return result;
  }catch{
    state.lastRun={startedAt,finishedAt:now().toISOString(),status:'review_failed',
      days:days.map(date=>({date,status:'review_required',seats:[]})),
      ledgerProtectedDates:[],ledgerReviewDates:[],coverage:null,
      inventoryComplete:false,safeToBook:false,bookingAuthorized:false};
    save();
    throw Error('Sichere Bestandsprüfung nicht abgeschlossen. Keine Buchung.');
  }finally{running=false;}
 }
 async function tick(){
   const current=now(), c=viennaClock(current);
   const weekday=['Mon','Tue','Wed','Thu','Fri'].indexOf(c.weekday);
   // If the server was offline Monday, catch up once Tue-Fri from 07:00.
   if(!enabled||running||weekday<0||c.time<'07:00')return false;
   const monday=new Date(c.date+'T00:00:00Z');
   monday.setUTCDate(monday.getUTCDate()-weekday);
   const week=monday.toISOString().slice(0,10);
   if(state.lastSchedule!==week){
     state.lastSchedule=week;
     state.attemptsThisWeek=0;
     state.nextRetryAt=null;
     save();
   }
   if(state.lastSuccessWeek===week || state.attemptsThisWeek>=2 ||
      (state.nextRetryAt && current.getTime()<Date.parse(state.nextRetryAt)))return false;
   // Persist the attempt before opening the provider browser: restart-safe.
   state.attemptsThisWeek+=1;
   state.nextRetryAt=null;
   save();
   try{
     const result=await run();
     if(result.status!=='inventory_batch_read')
       throw Error('WESTbahn-Kontobestand konnte nicht geprüft werden. Keine Buchung.');
     state.lastSuccessWeek=week;
     state.nextRetryAt=null;
     save();
     return true;
   }catch(e){
     // One additional attempt after 30 minutes; no unbounded polling.
     state.nextRetryAt=state.attemptsThisWeek<2
       ?new Date(current.getTime()+30*60_000).toISOString():null;
     save();
     throw e;
   }
 }
 return {run,tick,status};
}
