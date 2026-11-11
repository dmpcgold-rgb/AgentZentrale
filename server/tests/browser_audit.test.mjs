import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {createBrowser,sanitizeTicketAudit} from '../browser.mjs';

const DATE='2026-11-17',SEAT='191D';
const now=()=>new Date('2026-11-11T07:00:00Z');
const evidence=()=>({
 status:'ticket_detail_check',date:DATE,seat:SEAT,
 detailStatus:'detail_read',yearVerified:true,seatMatched:true,
 tripMatched:true,referenceVisible:true,dateExplicit:true,
 inventoryComplete:false,
 bookingAuthorized:false,confirmationVerified:false,
 bookingId:'PRIVATE-BOOKING-99999',ticketLink:'https://westbahn.at/private'
});
const runner=(raw, calls=[],exit=0)=> (python,args,options)=>{
 calls.push({python,args,options});
 const child=new EventEmitter();
 child.stdout=new EventEmitter();
 child.kill=()=>{};
 queueMicrotask(()=>{
  child.stdout.emit('data',Buffer.from(JSON.stringify(raw)));
  child.emit('close',exit);
 });
 return child;
};

test('known ticket is verified as existing but never authorizes booking',()=>{
 const r=sanitizeTicketAudit(evidence(),'ticket-detail-check',DATE,SEAT);
 assert.equal(r.status,'existing_ticket_verified');
 assert.equal(r.inventoryComplete,false);
 assert.equal(r.safeToBook,false);
 assert.equal(r.bookingAuthorized,false);
 assert.equal(r.confirmationVerified,false);
 assert.equal(r.checks.referenceVisible,true);
 assert.equal(JSON.stringify(r).includes('PRIVATE-BOOKING'),false);
 assert.equal(JSON.stringify(r).includes('ticketLink'),false);
});

test('incomplete detail, wrong seat, wrong date and untrusted output cannot verify',()=>{
 for(const raw of [
  {...evidence(),yearVerified:false},
  {...evidence(),seat:'233A'},
  {...evidence(),date:'2026-11-18'},
  {...evidence(),referenceVisible:false},
  {...evidence(),inventoryComplete:true},
  null,{status:'blocked'},'PASS'
 ]){
  const r=sanitizeTicketAudit(raw,'ticket-detail-check',DATE,SEAT);
  assert.equal(r.status,'review_required');
  assert.equal(r.bookingAuthorized,false);
 }
});

test('positive account cards are observed, never proof of an empty inventory',()=>{
 const r=sanitizeTicketAudit({
  status:'existing_ticket_visible',inventoryComplete:false,
  matches:[{seat:'191D',expectedSeat:true,yearExplicit:false}],
  bookingReference:'SECRET123'
 },'booking-check',DATE,SEAT);
 assert.equal(r.status,'existing_ticket_visible');
 assert.equal(r.safeToBook,false);
 assert.equal(r.inventoryComplete,false);
 assert.equal(JSON.stringify(r).includes('SECRET123'),false);
 const missing=sanitizeTicketAudit({
  status:'not_seen_in_incomplete_account',inventoryComplete:false,matches:[]
 },'booking-check',DATE,SEAT);
 assert.equal(missing.status,'review_required');
 assert.equal(missing.reason,'inventory_not_proven_complete');
});

test('audit worker passes only date and seat, and redacts provider identifiers',async()=>{
 const calls=[];
 const browser=createBrowser({env:{WESTBAHN_BROWSER_ENABLED:'true',
  WESTBAHN_PYTHON:'/opt/python',WESTBAHN_BROWSER_PROFILE:'/tmp/mock-profile'},
  now,execute:runner(evidence(),calls)});
 const r=await browser.run('ticket-detail-check',DATE,SEAT);
 assert.equal(r.status,'existing_ticket_verified');
 assert.deepEqual(calls[0].args.slice(-5),['ticket-detail-check','--date',DATE,'--seat',SEAT]);
 assert.equal(calls[0].python,'/opt/python');
 assert.equal(JSON.stringify(r).includes('PRIVATE-BOOKING'),false);
 assert.equal(browser.status().liveBooking,false);
});

test('ticket audit rejects invalid date and seat without launching browser',async()=>{
 const calls=[];
 const browser=createBrowser({env:{WESTBAHN_BROWSER_ENABLED:'true'},
  now,execute:runner(evidence(),calls)});
 for(const [date,seat] of [
  ['2026-11-32','191D'],['2026-11-17','BAD'],['2026-11-17','191D;rm'],
  ['2025-11-17','191D'],['2027-12-17','191D']
 ]){
  await assert.rejects(browser.run('ticket-detail-check',date,seat));
 }
 await assert.rejects(browser.run('purchase',DATE,SEAT));
 assert.equal(calls.length,0);
});

test('browser audit is disabled when profile feature is not enabled',async()=>{
 const b=createBrowser({env:{WESTBAHN_BROWSER_ENABLED:'false'},now,
  execute:()=>{throw Error('must not start');}});
 await assert.rejects(b.run('ticket-detail-check',DATE,SEAT),/nicht aktiviert/);
});

test('nonzero worker exit refuses audit result',async()=>{
 const b=createBrowser({env:{WESTBAHN_BROWSER_ENABLED:'true'},now,
  execute:runner(evidence(),[],1)});
 await assert.rejects(b.run('ticket-detail-check',DATE,SEAT),/fehlgeschlagen/);
});

test('existing probe and prepare still work in search-only mode',async()=>{
 const p=createBrowser({env:{WESTBAHN_BROWSER_ENABLED:'true'},now,
   execute:runner({status:'reachable'})});
 assert.equal((await p.run('probe')).status,'reachable');
 const q=createBrowser({env:{WESTBAHN_BROWSER_ENABLED:'true'},now,
   execute:runner({status:'connection_found'})});
 assert.equal((await q.run('prepare',DATE)).status,'connection_found');
});

test('invalid or oversized browser response never becomes proof of a ticket',async()=>{
 const browser=createBrowser({env:{WESTBAHN_BROWSER_ENABLED:'true'},now,
   execute:runner({status:'ticket_detail_check',inventoryComplete:false})});
 const r=await browser.run('ticket-detail-check',DATE,SEAT);
 assert.equal(r.status,'review_required');
 assert.equal(r.bookingAuthorized,false);
});
