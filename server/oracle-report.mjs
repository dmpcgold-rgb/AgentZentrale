import {readFile} from 'node:fs/promises';
const date = v => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v);
const days = v => Array.isArray(v) && v.length<=370 && v.every(date);
export function normalizeBookingReport(v){
 if(!v || !days(v.bereits_gebucht)||!days(v.neu_gebucht)||!days(v.offene_gepruefte_tage)
 ||!Number.isInteger(v.gesamt_bestaetigt)||v.gesamt_bestaetigt<0
 ||!(v.lueckenlos_bis===null||date(v.lueckenlos_bis))
 ||typeof v.erstellt!=='string'||!Number.isFinite(Date.parse(v.erstellt))
 ||!['success','exit-code','unknown','timeout','signal','core-dump','resources','watchdog','start-limit-hit','oom-kill','protocol'].includes(v.dienst_status)
 ||typeof v.fehler_oder_luecken!=='boolean') throw new Error('Invalid report');
 const confirmed=new Set([...v.bereits_gebucht,...v.neu_gebucht]);
 if(confirmed.size!==v.gesamt_bestaetigt||v.offene_gepruefte_tage.some(d=>confirmed.has(d)))throw new Error('Inconsistent report');
 return {erstellt:v.erstellt,dienst_status:v.dienst_status,bereits_gebucht:v.bereits_gebucht,neu_gebucht:v.neu_gebucht,gesamt_bestaetigt:v.gesamt_bestaetigt,lueckenlos_bis:v.lueckenlos_bis,offene_gepruefte_tage:v.offene_gepruefte_tage,fehler_oder_luecken:v.fehler_oder_luecken};
}
export async function readBookingReport(path){
 if(!path)return {available:false,report:null};
 try{const raw=await readFile(path,'utf8');if(raw.length>100000)throw new Error('Report too large');return {available:true,report:normalizeBookingReport(JSON.parse(raw))};}
 catch{return {available:false,report:null};}
}
