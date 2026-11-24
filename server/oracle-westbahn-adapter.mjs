/**
 * Read-only bridge to the existing private Oracle WESTbahn worker.
 *
 * Does not copy credentials, parse private ticket identifiers or invoke
 * checkout scripts. The worker's visible-card scan is NOT authoritative proof
 * that a ticket is absent. A live provider adapter requires a separate,
 * audited implementation of the booking protocol.
 */
import {execFile as execFileCallback} from 'node:child_process';
import {promisify} from 'node:util';
import {resolve} from 'node:path';

const execFile=promisify(execFileCallback);
const DATE=/^\d{4}-\d{2}-\d{2}$/;
const WORKER='/app/server/browser/worker.py';

function validDate(value){
 if(typeof value!=='string'||!DATE.test(value))return false;
 const d=new Date(value+'T00:00:00Z');
 return !Number.isNaN(d.valueOf())&&d.toISOString().slice(0,10)===value;
}
export function summarizeReadOnlyEvidence(value,date){
 if(!validDate(date))throw new Error('Ungültiges Reisedatum');
 if(!value||typeof value!=='object'||Array.isArray(value))
   return {status:'unknown',accountVerified:false,inventoryComplete:false,reason:'invalid_inventory_response'};
 // The legacy Oracle worker explicitly returns inventoryComplete=false and
 // absenceEvidence.status=not_proven. Never promote this to status='none'.
 const candidate=value.potentialDuplicate===true ||
   value.absenceEvidence?.status==='positive_booking_evidence';
 return {
   status:'unknown',
   accountVerified:value.status==='inventory_evidence_inspected' && value.pagesVerified>0 && value.pagesFailed===0,
   inventoryComplete:false,
   searchedDate:date,
   matchingTicketFound:candidate ? true : null,
   searchComplete:false,
   possibleExisting:candidate,
   reason:candidate?'possible_existing_reservation':'provider_absence_not_authoritative'
 };
}
export function createAdapter({
  workerPath=WORKER,
  pythonBin='python3',
  execute=execFile
}={}){
 if(typeof workerPath!=='string'||!workerPath.startsWith('/')||workerPath.includes('..'))
   throw new Error('Worker-Pfad muss absolut und ohne Traversal sein');
 if(typeof execute!=='function')throw new Error('Ungültiger Runner');
 const read=async date=>{
   if(!validDate(date))throw new Error('Ungültiges Reisedatum');
   try{
     const {stdout}=await execute(pythonBin,[resolve(workerPath),'reservation-pages-check','--date',date],
       {timeout:65000,maxBuffer:512*1024,windowsHide:true});
     const parsed=JSON.parse(stdout.trim());
     if(parsed.date!==date)throw new Error('Falscher Reisetag');
     return summarizeReadOnlyEvidence(parsed,date);
   }catch{
     return {status:'unknown',accountVerified:false,inventoryComplete:false,
       searchComplete:false,reason:'read_only_account_check_unavailable'};
   }
 };
 const disabled=async()=>{throw new Error(
   'Oracle-Adapter ist nur lesend. Buchung, Preisangebot und Sitzplatzsuche sind nicht freigeschaltet.'
 );};
 return {
   mode:'read_only',
   capabilities:{liveCheckout:false,authoritativeAbsence:false},
   existing:async ({date})=>read(date),
   search:disabled,
   quote:disabled,
   book:disabled
 };
}
