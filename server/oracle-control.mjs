import {writeFile,rename,unlink,readFile} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {join} from 'node:path';
export function validateControl(body){
 if(!body||body.confirm!=='WESTBAHN-STEUERUNG'||!['pause','resume','schedule','horizon','book_now','stop_booking'].includes(body.action))throw new Error('Ungültige Steuerungsfreigabe.');
 if(body.action==='schedule'&&(typeof body.time!=='string'||!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(body.time)))throw new Error('Uhrzeit muss HH:MM sein.');
 if(body.action==='horizon'){
  if(!Number.isInteger(body.months)||body.months<1||body.months>6)throw new Error('Buchungsvorlauf muss 1 bis 6 Monate betragen.');
  return {action:'horizon',months:body.months};
 }
 return {action:body.action,...(body.action==='schedule'?{time:body.time}:{})};
}
export async function enqueueControl(dir,body){
 const command=validateControl(body),id=randomUUID();
 const tmp=join(dir,id+'.tmp'),dest=join(dir,id+'.json');
 try{await writeFile(tmp,JSON.stringify({...command,id,created:Date.now()/1000}),{flag:'wx',mode:0o600});await rename(tmp,dest);}
 catch(e){await unlink(tmp).catch(()=>{});throw e;}
 return {id,accepted:true};
}
export async function controlResult(dir,id){
 if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id))throw new Error('Invalid ID');
 try{const v=JSON.parse(await readFile(join(dir,id+'.json'),'utf8'));return {id,status:v.id===id&&v.ok===true?'completed':'failed'};}
 catch(e){if(e.code==='ENOENT')return {id,status:'pending'};throw e;}
}
