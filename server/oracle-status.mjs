import {readFile} from 'node:fs/promises';
export function normalizeHostStatus(v, now=Date.now()){
 const stamp=Date.parse(v?.timestamp);
 if(!Number.isFinite(stamp)||stamp>now+5000||now-stamp>120000)throw new Error('Stale status');
 const active=['active','inactive','activating','deactivating','failed','reloading','maintenance'];
 if(!active.includes(v.timer?.ActiveState)||!active.includes(v.service?.ActiveState))throw new Error('Invalid state');
 const safe=(x)=>typeof x==='string'&&x.length<=120&&!/[\r\n]/.test(x)?x:null;
 const p=v.progress;
 const day=x=>typeof x==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(x)?x:null;
 const dates=x=>Array.isArray(x)&&x.length<=370&&x.every(d=>day(d))?[...new Set(x)]:[];
 const progress=p&&typeof p==='object'?{currentDay:day(p.currentDay),phase:['checking','confirmed','new','retry','stopped','skipped'].includes(p.phase)?p.phase:null,confirmed:dates(p.confirmed),newlyBooked:dates(p.newlyBooked),updatedAt:safe(p.updatedAt)}:null;
 return {progress,monthsAhead:Number.isInteger(v.monthsAhead)&&v.monthsAhead>=1&&v.monthsAhead<=6?v.monthsAhead:null,timestamp:v.timestamp,telegramConfigured:v.telegramConfigured===true,timer:{active:v.timer.ActiveState,enabled:v.timer.UnitFileState==='enabled',next:safe(v.timer.NextElapseUSecRealtime)},service:{active:v.service.ActiveState,result:safe(v.service.Result)}};
}
export async function readHostStatus(path){
 if(!path)return {available:false,status:null};
 try{const raw=await readFile(path,'utf8');if(raw.length>16000)throw new Error('Too large');return {available:true,status:normalizeHostStatus(JSON.parse(raw))};}
 catch{return {available:false,status:null};}
}
