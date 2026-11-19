/** One bounded, privacy-preserving read-only Gmail check per weekly review.
 * No provider booking request, no mail credentials in process arguments,
 * and no secret/ticket identifiers in returned results or logs.
 */
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const execute=promisify(execFile);
const PYTHON=resolve(dirname(fileURLToPath(import.meta.url)),'browser/gmail_ticket_confirmation.py');
const ISO=/^\d{4}-\d{2}-\d{2}$/;
const SEAT=/^\d{3}[A-D]$/;

export function validateWeeklyEmailEvidence(raw,expectedDates){
 const base={status:'email_read_unavailable',confirmed:[],
   conflictingDates:[],bookingAuthorized:false};
 if(!raw||typeof raw!=='object'||Array.isArray(raw))return base;
 if(!['email_week_checked','email_not_configured','email_invalid_configuration',
       'email_read_unavailable'].includes(raw.status)||
    raw.bookingAuthorized!==false)return base;
 if(raw.status!=='email_week_checked')
   return {...base,status:raw.status};
 if(!Array.isArray(raw.confirmed)||raw.confirmed.length>5||
    !Array.isArray(raw.conflictingDates)||raw.conflictingDates.length>5)return base;
 const confirmed=[],seen=new Set(),conflicts=new Set();
 for(const date of raw.conflictingDates){
   if(!expectedDates.includes(date)||conflicts.has(date))return base;
   conflicts.add(date);
 }
 for(const item of raw.confirmed){
   if(!item||!expectedDates.includes(item.date)||!ISO.test(item.date)||
      !SEAT.test(item.seat)||item.source!=='official_email'||
      seen.has(item.date)||conflicts.has(item.date))return base;
   seen.add(item.date);
   confirmed.push({date:item.date,seat:item.seat,source:'official_email'});
 }
 return {status:'email_week_checked',confirmed,
   conflictingDates:[...conflicts].sort(),bookingAuthorized:false};
}

export function createWeeklyGmailConfirmation({
 env=process.env,exec=execute
}={}){
 return async dates=>{
  if(env.WESTBAHN_GMAIL_CONFIRMATION_ENABLED!=='1')
   return {status:'email_not_configured',confirmed:[],
      conflictingDates:[],bookingAuthorized:false};
  if(!Array.isArray(dates)||dates.length<1||dates.length>5||
     new Set(dates).size!==dates.length||
     dates.some(d=>typeof d!=='string'||!ISO.test(d)))
   throw Error('Ungültige Reisetage für E-Mail-Abgleich.');
  try{
   const {stdout}=await exec(env.WESTBAHN_PYTHON||'python3',
     [PYTHON,'--dates',dates.join(','),'--train','1009'],
     {env,timeout:45_000,maxBuffer:16_384,windowsHide:true});
   return validateWeeklyEmailEvidence(JSON.parse(stdout),dates);
  }catch{
   return {status:'email_read_unavailable',confirmed:[],
     conflictingDates:[],bookingAuthorized:false};
  }
 };
}
