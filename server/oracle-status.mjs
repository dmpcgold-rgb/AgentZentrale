import {readFile} from 'node:fs/promises';
export function normalizeHostStatus(v, now=Date.now()){
 const stamp=Date.parse(v?.timestamp);
 if(!Number.isFinite(stamp)||stamp>now+5000||now-stamp>120000)throw new Error('Stale status');
 const active=['active','inactive','activating','deactivating','failed','reloading','maintenance'];
 if(!active.includes(v.timer?.ActiveState)||!active.includes(v.service?.ActiveState))throw new Error('Invalid state');
 const safe=(x)=>typeof x==='string'&&x.length<=120&&!/[\r\n]/.test(x)?x:null;
 return {timestamp:v.timestamp,timer:{active:v.timer.ActiveState,enabled:v.timer.UnitFileState==='enabled',next:safe(v.timer.NextElapseUSecRealtime)},service:{active:v.service.ActiveState,result:safe(v.service.Result)}};
}
export async function readHostStatus(path){
 if(!path)return {available:false,status:null};
 try{const raw=await readFile(path,'utf8');if(raw.length>16000)throw new Error('Too large');return {available:true,status:normalizeHostStatus(JSON.parse(raw))};}
 catch{return {available:false,status:null};}
}
