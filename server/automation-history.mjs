import { readFileSync, writeFileSync, renameSync, mkdirSync, unlinkSync } from 'node:fs';
import { dirname } from 'node:path';
import { randomUUID } from 'node:crypto';
const valid = row => row && typeof row.id==='string' && /^[a-zA-Z0-9_-]{8,80}$/.test(row.id) && typeof row.type==='string' && /^[a-z-]{1,60}$/.test(row.type) && ['completed','failed'].includes(row.status) && typeof row.at==='string' && Number.isFinite(Date.parse(row.at));
export function createAutomationHistory(file){
 let items=[], healthy=true;
 if(file){try{const data=JSON.parse(readFileSync(file,'utf8'));if(!Array.isArray(data)||!data.every(valid))throw Error('invalid history');items=data.slice(0,100).map(({id,type,status,at})=>({id,type,status,at}));}catch(e){if(e.code!=='ENOENT')healthy=false;}}
 return {
  list:()=>items.map(x=>({...x})),
  persistent:()=>Boolean(file&&healthy),
  record(row){
   if(!valid(row))return;
   items.unshift({id:row.id,type:row.type,status:row.status,at:row.at});items=items.slice(0,100);
   if(!file||!healthy)return;
   const tmp=file+'.'+randomUUID()+'.tmp';
   try{mkdirSync(dirname(file),{recursive:true,mode:0o700});writeFileSync(tmp,JSON.stringify(items),{mode:0o600,flag:'wx'});renameSync(tmp,file);}catch{healthy=false;try{unlinkSync(tmp);}catch{}}
  }
 };
}
