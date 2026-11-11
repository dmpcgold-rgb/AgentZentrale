import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createWestbahn} from '../westbahn.mjs';
import {applyVerifiedBatch,createWeeklyReview} from '../weekly-review.mjs';
import {planDates} from '../../src/core/westbahn.js';

const now=()=>new Date('2026-11-16T06:00:00Z'); // Monday 07:00 Vienna
const dates=()=>planDates(now()).slice(0,5);
const item=(date,status='review_required',seat=null)=>({
 date,status,seats:seat?[seat]:[],dateVerified:status==='detail_verified',
 detailVerified:status==='detail_verified',potentialDuplicate:seat!==null,
 safeToBook:false
});
const batch=()=>({
 status:'inventory_batch_read',accountPageReads:4,
 inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
 days:dates().map((d,i)=>i===0?item(d,'detail_verified','191D'):item(d))
});
const fakeBrowser=(snapshot,seen=[])=>({
 async run(...args){seen.push(args);return snapshot;}
});

test('strictly verified account ticket becomes persistent no-duplicate lock',()=>{
 const ledger=createWestbahn({now});
 const result=applyVerifiedBatch(batch(),dates(),ledger);
 assert.deepEqual(result.ledgerProtectedDates,[dates()[0]]);
 assert.equal(ledger.status().rows.find(r=>r.date===dates()[0]).status,'existing_verified');
 assert.equal(result.safeToBook,false);
 assert.equal(result.inventoryComplete,false);
 assert.equal(result.bookingAuthorized,false);
 assert.equal(result.days[1].status,'review_required');
});

test('malformed second day blocks ALL writebacks, including first day',()=>{
 const ledger=createWestbahn({now});
 const invalid=batch();
 invalid.days[1]={...invalid.days[1],seat:'SECRET-TOKEN',status:'detail_verified'};
 const result=applyVerifiedBatch(invalid,dates(),ledger);
 assert.equal(result.status,'review_required');
 assert.deepEqual(result.ledgerProtectedDates,[]);
 assert.deepEqual(ledger.status().rows,[]);
});

test('no visible card must never become a booking permission or a confirmed ticket',()=>{
 const ledger=createWestbahn({now});
 const quiet={...batch(),days:dates().map(d=>item(d))};
 const result=applyVerifiedBatch(quiet,dates(),ledger);
 assert.equal(result.status,'inventory_batch_read');
 assert.deepEqual(result.ledgerProtectedDates,[]);
 assert.ok(result.days.every(d=>!d.safeToBook));
 assert.deepEqual(ledger.status().rows,[]);
});

test('conflicting seats remain for manual review; original ledger stays untouched',()=>{
 const ledger=createWestbahn({now});
 ledger.recordUserReported(dates()[0],'233A');
 const result=applyVerifiedBatch(batch(),dates(),ledger);
 assert.deepEqual(result.ledgerProtectedDates,[]);
 assert.deepEqual(result.ledgerReviewDates,[dates()[0]]);
 const row=ledger.status().rows.find(r=>r.date===dates()[0]);
 assert.equal(row.seat,'233A');
 assert.equal(row.status,'user_reported');
});

test('Monday 7 Vienna scheduler runs only once even after restart',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'wb-readonly-'));
 try{
  const file=join(dir,'review.json'),ledgerFile=join(dir,'ledger.json');
  const seen=[],ledger=createWestbahn({now,file:ledgerFile});
  const browser=fakeBrowser(batch(),seen);
  const review=createWeeklyReview({browser,westbahn:ledger,now,file});
  assert.equal(await review.tick(),true);
  assert.equal(await review.tick(),false);
  assert.equal(seen.length,1);
  assert.deepEqual(seen[0],['inventory-batch',null,null,dates()]);
  assert.equal(review.status().lastRun.status,'inventory_batch_read');
  assert.deepEqual(review.status().lastRun.ledgerProtectedDates,[dates()[0]]);
  const restarted=createWeeklyReview({browser,westbahn:ledger,now,file});
  assert.equal(await restarted.tick(),false);
  assert.equal(ledger.status().rows.find(r=>r.date===dates()[0]).status,'existing_verified');
  assert.equal(seen.length,1);
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('not Monday or before 07:00 never starts a browser review',async()=>{
 const seen=[];
 const ledger=createWestbahn({now});
 const browser=fakeBrowser(batch(),seen);
 for(const at of ['2026-11-16T05:59:00Z','2026-11-17T06:00:00Z']){
  const review=createWeeklyReview({browser,westbahn:ledger,now:()=>new Date(at)});
  assert.equal(await review.tick(),false);
 }
 assert.equal(seen.length,0);
});

test('disabled Monday timer never runs, but explicitly requested read-only review works',async()=>{
 const seen=[];
 const review=createWeeklyReview({browser:fakeBrowser(batch(),seen),
  westbahn:createWestbahn({now}),now,enabled:false});
 assert.equal(await review.tick(),false);
 assert.equal(seen.length,0);
 const manual=await review.run();
 assert.equal(manual.status,'inventory_batch_read');
 assert.equal(seen.length,1);
 assert.equal(review.status().enabled,false);
});

test('failed account read is logged as uncertain and never buys',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'wb-unavailable-'));
 try{
  const file=join(dir,'review.json'),ledger=createWestbahn({now});
  const browser={async run(){throw Error('private provider data');}};
  const review=createWeeklyReview({browser,westbahn:ledger,now,file});
  await assert.rejects(review.tick(),/Keine Buchung/);
  assert.equal(review.status().lastRun.status,'review_failed');
  assert.equal(JSON.stringify(review.status()).includes('private provider data'),false);
  assert.ok(review.status().lastRun.days.every(x=>x.status==='review_required'));
  assert.equal(await review.tick(),false);
  assert.deepEqual(ledger.status().rows,[]);
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('negative account evidence or claimed purchase authorization fails closed',()=>{
 const ledger=createWestbahn({now});
 for(const changes of [
   {inventoryComplete:true},{safeToBook:true},{bookingAuthorized:true},
   {status:'complete'},{days:[]}
 ]){
   const result=applyVerifiedBatch({...batch(),...changes},dates(),ledger);
   assert.equal(result.status,'review_required');
   assert.deepEqual(result.ledgerProtectedDates,[]);
 }
 assert.deepEqual(ledger.status().rows,[]);
});


test('failed Monday account read retries only once after 30 minutes, never buys',async()=>{
 let clock=new Date('2026-11-16T06:00:00Z');
 const current=()=>clock;
 let calls=0;
 const p=createWestbahn({now:current});
 const browser={async run(){calls++;if(calls===1)throw Error('provider temporarily offline');
   const days=planDates(current()).slice(0,5);
   return {status:'inventory_batch_read',accountPageReads:4,
    inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
    days:days.map(d=>item(d))};
 }};
 const review=createWeeklyReview({now:current,browser,westbahn:p});
 await assert.rejects(review.tick(),/Keine Buchung/);
 assert.equal(review.status().attemptsThisWeek,1);
 assert.equal(review.status().lastSuccessWeek,null);
 assert.ok(review.status().nextRetryAt);
 assert.equal(await review.tick(),false);
 clock=new Date('2026-11-16T06:29:00Z');
 assert.equal(await review.tick(),false);
 clock=new Date('2026-11-16T06:30:00Z');
 assert.equal(await review.tick(),true);
 assert.equal(review.status().lastSuccessWeek,'2026-11-16');
 assert.equal(review.status().attemptsThisWeek,2);
 assert.equal(await review.tick(),false);
 assert.equal(calls,2);
 assert.deepEqual(p.status().rows,[]);
});

test('two failed attempts stop retrying for that week',async()=>{
 let clock=new Date('2026-11-16T06:00:00Z'),calls=0;
 const current=()=>clock;
 const review=createWeeklyReview({now:current,westbahn:createWestbahn({now:current}),
  browser:{async run(){calls++;throw Error('provider unavailable');}}});
 await assert.rejects(review.tick(),/Keine Buchung/);
 clock=new Date('2026-11-16T06:31:00Z');
 await assert.rejects(review.tick(),/Keine Buchung/);
 assert.equal(review.status().attemptsThisWeek,2);
 assert.equal(review.status().nextRetryAt,null);
 clock=new Date('2026-11-20T10:00:00Z');
 assert.equal(await review.tick(),false);
 assert.equal(calls,2);
});

test('server restart after missed Monday catches up Tuesday and retains success',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'wb-catchup-'));
 try{
  const file=join(dir,'review.json'),ledger=createWestbahn({now:()=>new Date('2026-11-17T06:15:00Z')});
  const now=()=>new Date('2026-11-17T06:15:00Z');
  let runs=0;
  const browser={async run(mode,day,seat,days){
   assert.equal(mode,'inventory-batch');
   assert.equal(days[0],'2026-11-17');
   runs++;
   return {status:'inventory_batch_read',accountPageReads:4,
     inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
     days:days.map(x=>item(x))};
  }};
  const review=createWeeklyReview({now,file,westbahn:ledger,browser});
  assert.equal(await review.tick(),true);
  assert.equal(review.status().lastSchedule,'2026-11-16');
  assert.equal(review.status().lastSuccessWeek,'2026-11-16');
  const restarted=createWeeklyReview({now,file,westbahn:ledger,browser});
  assert.equal(await restarted.tick(),false);
  assert.equal(runs,1);
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('weekend does not start catch-up audit, and pre-seven remains disabled',async()=>{
 const dates=['2026-11-14T06:30:00Z','2026-11-15T07:00:00Z','2026-11-17T05:59:00Z'];
 let calls=0;
 for(const date of dates){
  const review=createWeeklyReview({now:()=>new Date(date),
    westbahn:createWestbahn({now:()=>new Date(date)}),
    browser:{async run(){calls++;throw Error('never run');}}});
  assert.equal(await review.tick(),false);
 }
 assert.equal(calls,0);
});

test('read-only review reports unavailable account without claiming completed scan',async()=>{
 const now=()=>new Date('2026-11-16T06:00:00Z');
 const days=planDates(now()).slice(0,5);
 const review=createWeeklyReview({now,westbahn:createWestbahn({now}),
   browser:{async run(){
     return {status:'review_required',inventoryComplete:false,
       bookingAuthorized:false,safeToBook:false,
       days:days.map(d=>item(d))};
   }}});
 await assert.rejects(review.tick(),/konnte nicht geprüft werden/);
 assert.equal(review.status().lastRun.status,'review_required');
 assert.equal(review.status().lastSuccessWeek,null);
 assert.equal(review.status().attemptsThisWeek,1);
});


test('retry timestamp and attempt count survive a server restart',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'wb-retry-reboot-'));
 try{
  let clock=new Date('2026-11-16T06:00:00Z');
  const now=()=>clock,file=join(dir,'review.json'),ledger=createWestbahn({now});
  let calls=0;
  const browser={async run(mode,travelDate,seat,days){
   calls++;
   if(calls===1)throw Error('offline');
   return {status:'inventory_batch_read',accountPageReads:4,
    inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
    days:days.map(x=>item(x))};
  }};
  const first=createWeeklyReview({now,file,westbahn:ledger,browser});
  await assert.rejects(first.tick(),/Keine Buchung/);
  clock=new Date('2026-11-16T06:15:00Z');
  const rebooted=createWeeklyReview({now,file,westbahn:ledger,browser});
  assert.equal(rebooted.status().attemptsThisWeek,1);
  assert.equal(await rebooted.tick(),false);
  clock=new Date('2026-11-16T06:31:00Z');
  assert.equal(await rebooted.tick(),true);
  assert.equal(rebooted.status().attemptsThisWeek,2);
  assert.equal(rebooted.status().lastSuccessWeek,'2026-11-16');
  assert.equal(calls,2);
 }finally{rmSync(dir,{recursive:true,force:true});}
});

test('the scheduled review saves only sanitized coverage, never private provider data',async()=>{
 const now=()=>new Date('2026-11-16T06:00:00Z');
 const days=planDates(now()).slice(0,5);
 const browser={async run(){return {
   status:'inventory_batch_read',accountPageReads:3,
   coverage:{pagesAttempted:4,pagesVerified:3,pagesFailed:1,
    domainsRead:2,complete:false,reason:'page_error_or_login',
    customerReference:'SECRET-NEVER-PERSIST'},
   inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
   secret:'SHOULD_NOT_PERSIST',days:days.map(x=>item(x))
 };}};
 const review=createWeeklyReview({browser,now,westbahn:createWestbahn({now})});
 const output=await review.run();
 assert.equal(output.coverage.pagesFailed,1);
 assert.equal(review.status().lastRun.coverage.pagesVerified,3);
 const serialized=JSON.stringify(review.status());
 assert.equal(serialized.includes('SECRET-NEVER-PERSIST'),false);
 assert.equal(serialized.includes('SHOULD_NOT_PERSIST'),false);
 assert.equal(output.inventoryComplete,false);
 assert.equal(output.bookingAuthorized,false);
});
