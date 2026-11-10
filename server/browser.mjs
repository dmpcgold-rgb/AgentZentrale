import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {planDates} from '../src/core/westbahn.js';
const script=resolve(dirname(fileURLToPath(import.meta.url)),'browser/worker.py');
export function createBrowser({env=process.env,execute=spawn,now=()=>new Date()}={}){
 let busy=false;
 const enabled=env.WESTBAHN_BROWSER_ENABLED==='true';
 const profile=resolve(env.WESTBAHN_BROWSER_PROFILE||'./data/westbahn-browser');
 const status=()=>({enabled,busy,profilePresent:existsSync(resolve(profile,'chromium')),liveBooking:false,mode:'search-only'});
 async function run(mode,date){
  if(!enabled)throw new Error('Browser auf dem Server noch nicht aktiviert.');
  if(busy)throw new Error('Browser ist bereits in Benutzung.');
  if(!['probe','prepare'].includes(mode))throw new Error('Nicht erlaubter Browserbefehl.');
  if(mode==='prepare'&&!planDates(now()).includes(date))throw new Error('Reisedatum nicht im erlaubten Wochenplan.');
  busy=true;
  try{return await new Promise((resolve,reject)=>{
   let out='', settled=false;const args=[script,mode,...(mode==='prepare'?['--date',date]:[])];
   const child=execute(env.WESTBAHN_PYTHON||'python3',args,{env:{...env,WESTBAHN_BROWSER_PROFILE:profile},stdio:['ignore','pipe','ignore']});
   const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(value);};
   const timer=setTimeout(()=>{child.kill('SIGKILL');finish(new Error('Browser-Zeitlimit erreicht. Keine Buchung.'));},65_000);
   child.stdout.on('data',b=>{out+=b;if(out.length>8192){child.kill('SIGKILL');finish(new Error('Browserantwort zu groß.'));}});
   child.on('error',()=>finish(new Error('Playwright-Browser konnte nicht gestartet werden.')));
   child.on('close',()=>{try{const result=JSON.parse(out);if(!['reachable','blocked','search_submitted','connection_found'].includes(result.status))throw new Error();finish(null,result);}catch{finish(new Error('Browser lieferte kein eindeutiges Ergebnis.'));}});
  });}finally{busy=false;}
 }
 return {status,run};
}
