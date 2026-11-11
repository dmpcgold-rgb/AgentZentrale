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

test('disabled weekly checks never run; manual run also blocked',async()=>{
 const seen=[];
 const review=createWeeklyReview({browser:fakeBrowser(batch(),seen),
  westbahn:createWestbahn({now}),now,enabled:false});
 assert.equal(await review.tick(),false);
 await assert.rejects(review.run(),/nicht aktiviert/);
 assert.equal(seen.length,0);
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
