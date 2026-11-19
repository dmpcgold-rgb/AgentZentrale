import {readFileSync,writeFileSync,renameSync,mkdirSync} from 'node:fs';
import {dirname} from 'node:path';

export const DEFAULT_RESERVATION_PLAN=Object.freeze({
 origin:'Wien Meidling',destination:'Wiener Neustadt Hbf',
 departure:'18:22',weekdays:[1,2,3,4,5],horizon:'2w',
 bookingWindowStart:'07:00',bookingWindowEnd:'19:00'
});
export const HORIZONS=Object.freeze(['1w','2w','4w','2m','6m']);
const VALID_HHMM=/^(?:[01]\d|2[0-3]):[0-5]\d$/;
function isValidStation(value){
 return typeof value==='string'&&value.trim()===value&&value.length>=3&&
  value.length<=100&&!/[<>\x00-\x1f]/.test(value);
}
export function validateReservationPlan(value){
 if(!value||typeof value!=='object'||Array.isArray(value))
   throw Error('Ungültige Reservierungseinstellungen.');
 const keys=Object.keys(DEFAULT_RESERVATION_PLAN);
 if(Object.keys(value).some(key=>!keys.includes(key)))
   throw Error('Unbekannte Reservierungseinstellung.');
 const plan={...DEFAULT_RESERVATION_PLAN,...value};
 if(!isValidStation(plan.origin)||!isValidStation(plan.destination)||
    plan.origin.toLocaleLowerCase('de')===plan.destination.toLocaleLowerCase('de'))
   throw Error('Start- und Zielbahnhof müssen unterschiedlich und gültig sein.');
 if(!VALID_HHMM.test(plan.departure)||!VALID_HHMM.test(plan.bookingWindowStart)||
    !VALID_HHMM.test(plan.bookingWindowEnd)||
    plan.bookingWindowStart>=plan.bookingWindowEnd)
   throw Error('Uhrzeiten müssen HH:MM sein; das Reservierungsfenster muss aufsteigend sein.');
 if(!Array.isArray(plan.weekdays)||!plan.weekdays.length||plan.weekdays.length>7||
    plan.weekdays.some(day=>!Number.isInteger(day)||day<1||day>7)||
    new Set(plan.weekdays).size!==plan.weekdays.length)
   throw Error('Bitte mindestens einen gültigen Wochentag wählen.');
 if(!HORIZONS.includes(plan.horizon))
   throw Error('Ungültiger Vorbuchungszeitraum.');
 return {...plan,weekdays:[...plan.weekdays].sort((a,b)=>a-b)};
}
const iso=d=>d.toISOString().slice(0,10);
function advanceHorizon(start,horizon){
 const out=new Date(start);
 const weeks={'1w':7,'2w':14,'4w':28};
 if(weeks[horizon])out.setUTCDate(out.getUTCDate()+weeks[horizon]-1);
 else{
   const months=horizon==='2m'?2:6;
   const day=out.getUTCDate();
   out.setUTCDate(1);
   out.setUTCMonth(out.getUTCMonth()+months);
   const last=new Date(Date.UTC(out.getUTCFullYear(),out.getUTCMonth()+1,0)).getUTCDate();
   out.setUTCDate(Math.min(day,last));
 }
 return out;
}
export function reservationDates(plan,at=new Date(),clock=null){
 const config=validateReservationPlan(plan);
 const local=clock||Object.fromEntries(new Intl.DateTimeFormat('en-CA',{
  timeZone:'Europe/Vienna',year:'numeric',month:'2-digit',day:'2-digit',
  hour:'2-digit',minute:'2-digit',hourCycle:'h23'
 }).formatToParts(at).map(x=>[x.type,x.value]));
 const today=local.date||`${local.year}-${local.month}-${local.day}`;
 const start=new Date(today+'T00:00:00Z');
 if(Number.isNaN(start.getTime()))throw Error('Ungültiges lokales Datum.');
 const end=advanceHorizon(start,config.horizon),days=new Set(config.weekdays);
 const out=[];
 for(let d=new Date(start);d<=end;d.setUTCDate(d.getUTCDate()+1)){
  const date=iso(d),weekday=d.getUTCDay()||7;
  if(days.has(weekday)&&(date!==today||`${local.hour||'00'}:${local.minute||'00'}`<config.departure))
   out.push(date);
 }
 return out;
}
// Only the exact tested WESTbahn leg can use the legacy browser/Gmail flow.
// A personalized leg needs an independently verified dynamic provider adapter.
export function isLegacyReservationPlan(plan){
 const value=validateReservationPlan(plan);
 return value.origin===DEFAULT_RESERVATION_PLAN.origin &&
  value.destination===DEFAULT_RESERVATION_PLAN.destination &&
  value.departure===DEFAULT_RESERVATION_PLAN.departure &&
  value.weekdays.join(',')===DEFAULT_RESERVATION_PLAN.weekdays.join(',') &&
  value.bookingWindowStart===DEFAULT_RESERVATION_PLAN.bookingWindowStart &&
  value.bookingWindowEnd===DEFAULT_RESERVATION_PLAN.bookingWindowEnd;
}

export function nextReservationBatch(plan,{at=new Date(),excludedDates=[],
  limit=5}={}){
 if(!Number.isInteger(limit)||limit<1||limit>5)
  throw Error('Maximal fünf Reisetage je Prüflauf.');
 if(!Array.isArray(excludedDates)||excludedDates.some(x=>
   typeof x!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(x)))
  throw Error('Ungültige ausgeschlossene Reisetage.');
 const blocked=new Set(excludedDates);
 return reservationDates(plan,at).filter(x=>!blocked.has(x)).slice(0,limit);
}
export function reservationWindowOpen(plan,at=new Date()){
 const config=validateReservationPlan(plan);
 const clock=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{
  timeZone:'Europe/Vienna',hour:'2-digit',minute:'2-digit',hourCycle:'h23'
 }).formatToParts(at).map(x=>[x.type,x.value]));
 const current=`${clock.hour}:${clock.minute}`;
 return current>=config.bookingWindowStart&&current<config.bookingWindowEnd;
}

export function createReservationPlanStore({file=null}={}){
 let current=DEFAULT_RESERVATION_PLAN;
 if(file){
  try{current=validateReservationPlan(JSON.parse(readFileSync(file,'utf8')));}
  catch(e){if(e.code!=='ENOENT')throw e;}
 }
 const get=()=>({...current,weekdays:[...current.weekdays]});
 const save=value=>{
  const next=validateReservationPlan(value);
  if(file){
   mkdirSync(dirname(file),{recursive:true,mode:0o700});
   writeFileSync(file+'.tmp',JSON.stringify(next),{mode:0o600});
   renameSync(file+'.tmp',file);
  }
  current=next;
  return get();
 };
 return {get,save};
}
