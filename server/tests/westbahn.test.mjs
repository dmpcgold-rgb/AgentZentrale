import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {RULES,planDates,chooseSeat,validateQuote,confirmedReceipt,viennaClock} from '../../src/core/westbahn.js';
import {createWestbahn,verifiedAccountReadback} from '../westbahn.mjs';
const now=()=>new Date('2026-11-16T06:00:00Z');
const day='2026-11-17';
const seat=(id,layout='opposite-table',groupSize=2)=>({id,layout,groupSize,available:true,class:'2+'});
const trip=(date=day)=>({date,origin:RULES.origin,destination:RULES.destination,departure:RULES.departure,class:RULES.class,ticket:RULES.ticket});
const quote=(over={})=>({...trip(),seat:'233A',quoteId:'q1',currency:'EUR',totalCents:0,...over});
const receipt=(over={})=>({...trip(),seat:'233A',bookingId:'TEST-123',confirmed:true,currency:'EUR',totalCents:0,...over});
function provider({price=0,fail=false,invalidReceipt=false,already=false,
    incompleteBefore=false,unverifiedBefore=false,readbackMissing=false,
    readbackWrongId=false,readbackWrongSource=false,readbackThrows=false}={}){
 let bookings=0,accountReads=0;
 return {
  get count(){return bookings},
  get reads(){return accountReads},
  existing:async({date})=>{
   if(date!==day)return {status:'none',accountVerified:true,inventoryComplete:true};
   accountReads++;
   if(bookings>0 && readbackThrows)throw Error('account timeout after checkout');
   if(already || (bookings>0 && !readbackMissing)){
    return {status:'confirmed',accountVerified:true,inventoryComplete:true,
      receiptSource:readbackWrongSource?'unknown':'provider_account',
      receipt:receipt(readbackWrongId?{bookingId:'OTHER-BOOKING-ID'}:{}),
      seat:{...seat('233A'),available:false}};
   }
   return {status:'none',accountVerified:!unverifiedBefore,
           inventoryComplete:!incompleteBefore};
  },
  search:async({date})=>date===day?{
    status:'available',...trip(date),connectionId:'c',
    seats:[seat('233D'),seat('233A'),seat('191D')]
  }:{status:'unavailable'},
  quote:async()=>quote({totalCents:price}),
  book:async({maxTotalCents,idempotencyKey})=>{
    assert.equal(maxTotalCents,0);
    assert.match(idempotencyKey,/2026-11-17/);
    bookings++;
    if(fail)throw Error('timeout');
    return receipt(invalidReceipt?{bookingId:''}:{});
  }
 };
}
test('Vienna DST and Monday schedule; weekdays only, six calendar months',()=>{assert.equal(viennaClock(now()).time,'07:00');assert.equal(viennaClock(new Date('2026-07-06T05:00:00Z')).time,'07:00');const dates=planDates(now());assert.equal(dates[0],day);assert.equal(dates.at(-1),'2027-05-14');assert.ok(dates.every(d=>![0,6].includes(new Date(d+'T00:00:00Z').getUTCDay())));assert.equal(planDates(new Date('2026-11-16T18:00:00Z'))[0],'2026-11-17');});
test('already reserved week excluded; first search starts 17 November',async()=>{const before=()=>new Date('2026-11-10T21:00:00Z');const dates=planDates(before());assert.deepEqual(dates.slice(0,5),['2026-11-17','2026-11-18','2026-11-19','2026-11-20','2026-11-23']);assert.equal(planDates(new Date('2026-11-20T20:00:00Z'))[0],'2026-11-23');const visited=[];const a=createWestbahn({now:before,adapter:{existing:async({date})=>{visited.push(date);return {status:'unknown'};}}});await a.run();assert.deepEqual(visited,dates);});
test('preferred seats beat alternatives; four seats and unknown layouts rejected',()=>{assert.equal(RULES.origin,'Wien Meidling');assert.equal(RULES.destination,'Wiener Neustadt Hbf');assert.equal(RULES.departure,'18:22');assert.equal(chooseSeat([seat('191D'),seat('233D')]).id,'233D');assert.equal(chooseSeat([seat('182A'),seat('191D')]).id,'191D');assert.equal(chooseSeat([seat('999A'),seat('182A')]).id,'182A');assert.equal(chooseSeat([seat('233D'),seat('191D'),seat('233A'),seat('233A','opposite-table',4)]).id,'233A');assert.equal(chooseSeat([seat('233A','opposite-table',4),seat('193B'),seat('999A')]).id,'193B');assert.equal(chooseSeat([seat('233A','unknown'),seat('233D','opposite-table',4)]),null);assert.equal(chooseSeat([seat('222A','offset'),seat('333A')]).id,'333A');});
test('only exact zero-euro quote and confirmed receipt accepted',()=>{assert.ok(validateQuote(quote(),day,'233A'));for(const q of [quote({totalCents:1}),quote({departure:'18:23'}),quote({class:'2'}),quote({seat:'233D'}),quote({currency:'USD'})])assert.equal(validateQuote(q,day,'233A'),false);assert.ok(confirmedReceipt(receipt(),day,'233A'));assert.equal(confirmedReceipt(receipt({bookingId:''}),day,'233A'),false);assert.equal(confirmedReceipt(receipt({confirmed:false}),day,'233A'),false);});
test('no live provider: scheduling and execution fail closed',async()=>{const a=createWestbahn({now});assert.equal(a.status().providerConnected,false);assert.throws(()=>a.setEnabled(true));await assert.rejects(a.run());assert.equal(await a.tick(),false);});
test('actual confirmed receipt recorded; no repeat checkout',async()=>{const p=provider();const a=createWestbahn({now,adapter:p});await a.run();assert.equal(p.count,1);assert.equal(a.status().rows.find(x=>x.date===day).status,'confirmed');assert.equal(a.status().confirmedThrough,day);await a.run();assert.equal(p.count,1);});
test('checkout requires an independently matched account receipt',async()=>{
 const p=provider();
 const a=createWestbahn({now,adapter:p});
 await a.run();
 assert.equal(p.count,1);
 assert.equal(p.reads,2,'account must be read both before and after checkout');
 assert.equal(a.status().rows.find(x=>x.date===day).status,'confirmed');
});

test('unauthenticated or incomplete account inventory must never trigger checkout',async()=>{
 for(const opts of [{incompleteBefore:true},{unverifiedBefore:true}]){
  const p=provider(opts),a=createWestbahn({now,adapter:p});
  await a.run();
  assert.equal(p.count,0);
  assert.equal(a.status().rows.find(x=>x.date===day).status,'blocked');
 }
});

test('missing, mismatched or unreachable account readback is uncertain, never retried',async()=>{
 for(const opts of [
  {readbackMissing:true},{readbackWrongId:true},
  {readbackWrongSource:true},{readbackThrows:true}
 ]){
  const p=provider(opts),a=createWestbahn({now,adapter:p});
  await a.run();
  assert.equal(a.status().rows.find(x=>x.date===day).status,'uncertain');
  await a.run();
  assert.equal(p.count,1,'a booking with unknown outcome must never be retried');
  assert.equal(a.status().confirmedThrough,null);
 }
});

test('readback accepts only account evidence for same booking ID and travel details',()=>{
 const evidence={status:'confirmed',accountVerified:true,inventoryComplete:true,
                 receiptSource:'provider_account',receipt:receipt()};
 assert.equal(verifiedAccountReadback(evidence,day,'233A','TEST-123'),true);
 for(const other of [
  {...evidence,receipt:receipt({bookingId:'OTHER'})},
  {...evidence,accountVerified:false},
  {...evidence,inventoryComplete:false},
  {...evidence,receiptSource:'checkout_banner'},
  {...evidence,receipt:receipt({date:'2026-11-18'})},
  {...evidence,receipt:receipt({seat:'191D'})}
 ]){
  assert.equal(verifiedAccountReadback(other,day,'233A','TEST-123'),false);
 }
});

test('positive price never booked',async()=>{const p=provider({price:1});const a=createWestbahn({now,adapter:p});await a.run();assert.equal(p.count,0);assert.equal(a.status().rows.find(x=>x.date===day).status,'blocked');});
test('missing confirmation and timeout never retried',async()=>{for(const p of [provider({fail:true}),provider({invalidReceipt:true})]){const a=createWestbahn({now,adapter:p});await a.run();assert.equal(a.status().rows.find(x=>x.date===day).status,'uncertain');await a.run();assert.equal(p.count,1);}});
test('existing provider booking prevents duplicate',async()=>{const p=provider({already:true});const a=createWestbahn({now,adapter:p});await a.run();assert.equal(p.count,0);assert.equal(a.status().confirmedThrough,day);});
test('durable ledger and weekly schedule survives restart',async()=>{const dir=mkdtempSync(join(tmpdir(),'az-westbahn-'));try{const file=join(dir,'ledger.json'),p=provider();const a=createWestbahn({now,adapter:p,file});a.setEnabled(true);assert.equal(await a.tick(),true);assert.equal(await a.tick(),false);const b=createWestbahn({now,adapter:p,file});assert.equal(b.status().confirmedThrough,day);assert.equal(await b.tick(),false);assert.equal(p.count,1);}finally{rmSync(dir,{recursive:true,force:true});}});

test('user-reported existing reservation persists and prevents any checkout for that date',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'az-existing-'));
 try{
  const file=join(dir,'ledger.json'),p=provider();
  const a=createWestbahn({now,adapter:p,file});
  a.recordUserReported(day,'191D');
  assert.equal(a.status().rows.find(x=>x.date===day).status,'user_reported');
  await a.run();
  assert.equal(p.count,0);
  const restarted=createWestbahn({now,adapter:p,file});
  await restarted.run();
  assert.equal(p.count,0);
  assert.equal(restarted.status().rows.find(x=>x.date===day).seat,'191D');
  assert.equal(restarted.status().confirmedThrough,null);
 }finally{rmSync(dir,{recursive:true,force:true});}
});
test('reported booking validation rejects corrupt input and conflicting updates',()=>{
 const a=createWestbahn({now});
 assert.throws(()=>a.recordUserReported('2026-02-30','191D'));
 assert.throws(()=>a.recordUserReported(day,'191E'));
 a.recordUserReported(day,'191D');
 assert.doesNotThrow(()=>a.recordUserReported(day,'191D'));
 assert.throws(()=>a.recordUserReported(day,'233A'));
});
