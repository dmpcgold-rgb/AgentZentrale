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
 const phases=['checking','confirmed','new','retry','stopped','skipped','bulk','bulk_done','bulk_unclear','cache','inventory','checkout','reconcile','timetable','pending_order','cancelled','conflict'];
 const events=Array.isArray(p?.events)?p.events.slice(-30).filter(e=>e&&phases.includes(e.phase)).map(e=>({phase:e.phase,day:day(e.day),count:Number.isInteger(e.count)&&e.count>=0&&e.count<=370?e.count:null})): [];
 const saved=dates(v.savedReservations);
 const pending=dates(v.pendingReservations);
 const reservations=Array.isArray(v.reservations)?v.reservations.slice(0,370).filter(r=>r&&day(r.date)&&saved.includes(r.date)).map(r=>({date:r.date,seat:typeof r.seat==='string'&&/^\d{3}[A-D]$/.test(r.seat)?r.seat:null,source:['official_email','manual_westbahn_verification','official_account','booking_report'].includes(r.source)?r.source:null})):null;
 const history=Array.isArray(v.history)?v.history.slice(0,20).filter(r=>r&&Number.isFinite(Date.parse(r.erstellt))).map(r=>({erstellt:safe(r.erstellt),dienst_status:['success','exit-code','signal','timeout','unknown'].includes(r.dienst_status)?r.dienst_status:'unknown',gesamt_bestaetigt:Number.isInteger(r.gesamt_bestaetigt)&&r.gesamt_bestaetigt>=0&&r.gesamt_bestaetigt<=370?r.gesamt_bestaetigt:null,neu_gebucht:dates(r.neu_gebucht),offene_gepruefte_tage:dates(r.offene_gepruefte_tage)})):null;
 const backupAt=safe(v.backupAt);
 const progress=p&&typeof p==='object'?{currentDay:day(p.currentDay),phase:phases.includes(p.phase)?p.phase:null,confirmed:dates(p.confirmed),newlyBooked:dates(p.newlyBooked),updatedAt:safe(p.updatedAt),events}:null;
 return {pendingReservations:Array.isArray(v.pendingReservations)?pending:null,reservations,history,backupAt,savedReservations:Array.isArray(v.savedReservations)?saved:null,progress,monthsAhead:Number.isInteger(v.monthsAhead)&&v.monthsAhead>=1&&v.monthsAhead<=6?v.monthsAhead:null,timestamp:v.timestamp,telegramConfigured:v.telegramConfigured===true,timer:{active:v.timer.ActiveState,enabled:v.timer.UnitFileState==='enabled',next:safe(v.timer.NextElapseUSecRealtime)},service:{active:v.service.ActiveState,result:safe(v.service.Result)}};
}
export async function readHostStatus(path){
 if(!path)return {available:false,status:null};
 try{const raw=await readFile(path,'utf8');if(raw.length>100000)throw new Error('Too large');return {available:true,status:normalizeHostStatus(JSON.parse(raw))};}
 catch{return {available:false,status:null};}
}
