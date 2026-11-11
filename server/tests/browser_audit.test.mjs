import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import {createBrowser,sanitizeTicketAudit,sanitizeBatchInventory,sanitizeOfflineSeatPreview} from '../browser.mjs';

const DATE='2026-11-17',SEAT='191D';
const now=()=>new Date('2026-11-11T07:00:00Z');
const evidence=()=>({
 status:'ticket_detail_check',date:DATE,seat:SEAT,
 detailStatus:'detail_read',yearVerified:true,seatMatched:true,
 tripMatched:true,referenceVisible:true,dateExplicit:true,
 inventoryComplete:false,safeToBook:false,
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

test('provider claims of booking permissions cannot be reused as read-only proof',()=>{
 for(const raw of [
  {...evidence(),bookingAuthorized:true},
  {...evidence(),safeToBook:true},
  {...evidence(),confirmationVerified:true},
  {...evidence(),status:'success_banner'}
 ]){
  assert.equal(sanitizeTicketAudit(raw,'ticket-detail-check',DATE,SEAT).status,'review_required');
 }
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


test('batch inventory reports observed cards without ever marking a day bookable',()=>{
 const dates=['2026-11-17','2026-11-18','2026-11-19'];
 const raw={status:'inventory_batch_read',accountPageReads:2,inventoryComplete:false,
  safeToBook:false,bookingAuthorized:false,privateReference:'SECRET-BOOKING',
  days:[
   {date:dates[0],status:'visible_year_verified',seats:['191D'],
     dateVerified:true,detailVerified:false,potentialDuplicate:true,safeToBook:false},
   {date:dates[1],status:'possible_existing',seats:['233A'],
     dateVerified:false,detailVerified:false,potentialDuplicate:true,safeToBook:false},
   {date:dates[2],status:'review_required',seats:[],
     dateVerified:false,detailVerified:false,potentialDuplicate:false,safeToBook:false}
  ]};
 const result=sanitizeBatchInventory(raw,dates);
 assert.equal(result.status,'inventory_batch_read');
 assert.equal(result.days.length,3);
 assert.equal(result.days[0].status,'visible_year_verified');
 assert.equal(result.days[2].status,'review_required');
 assert.equal(result.inventoryComplete,false);
 assert.equal(result.safeToBook,false);
 assert.equal(result.bookingAuthorized,false);
 assert.equal(JSON.stringify(result).includes('SECRET-BOOKING'),false);
});

test('batch inventory rejects forged complete inventory, unknown seat and wrong date',()=>{
 const dates=['2026-11-17'];
 const base={status:'inventory_batch_read',accountPageReads:1,
   inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
   days:[{date:dates[0],status:'visible_year_verified',
      seats:['191D'],dateVerified:true,detailVerified:false,potentialDuplicate:true,safeToBook:false}]};
 for(const bad of [
    {...base,inventoryComplete:true},
    {...base,safeToBook:true},
    {...base,bookingAuthorized:true},
    {...base,days:[{...base.days[0],seats:['SECRET']}]},
    {...base,days:[{...base.days[0],date:'2026-11-18'}]},
    {...base,days:[{...base.days[0],dateVerified:false}]},
    {...base,accountPageReads:0},
    {...base,days:[]}
 ]){
   const result=sanitizeBatchInventory(bad,dates);
   assert.equal(result.status,'review_required');
   assert.equal(result.days[0].status,'review_required');
   assert.equal(result.bookingAuthorized,false);
 }
});


test('fully matched provider detail within batch remains existing-only proof',()=>{
 const dates=['2026-11-17'];
 const raw={status:'inventory_batch_read',accountPageReads:4,
  inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
  days:[{date:dates[0],status:'detail_verified',seats:['191D'],
         dateVerified:true,detailVerified:true,potentialDuplicate:true,safeToBook:false}]};
 const result=sanitizeBatchInventory(raw,dates);
 assert.equal(result.status,'inventory_batch_read');
 assert.equal(result.days[0].status,'detail_verified');
 assert.equal(result.days[0].detailVerified,true);
 assert.equal(result.inventoryComplete,false);
 assert.equal(result.safeToBook,false);
 assert.equal(result.bookingAuthorized,false);
 for(const bad of [
   {...raw,days:[{...raw.days[0],detailVerified:false}]},
   {...raw,days:[{...raw.days[0],dateVerified:false}]},
   {...raw,days:[{...raw.days[0],potentialDuplicate:false}]},
   {...raw,days:[{...raw.days[0],seats:['191D','233A']}]},
   {...raw,days:[{...raw.days[0],date:'2026-11-18'}]}
 ]){
   assert.equal(sanitizeBatchInventory(bad,dates).status,'review_required');
 }
});

test('gateway exposes only bounded redacted coverage, never complete inventory',()=>{
 const dates=['2026-11-17'];
 const source={status:'inventory_batch_read',accountPageReads:3,
   safeToBook:false,bookingAuthorized:false,inventoryComplete:false,
   coverage:{pagesAttempted:4,pagesVerified:3,pagesFailed:1,domainsRead:2,
      complete:false,reason:'page_error_or_login',privateTicket:'DO_NOT_LEAK'},
   days:[{date:dates[0],status:'review_required',seats:[],
     dateVerified:false,detailVerified:false,potentialDuplicate:false,safeToBook:false}]
 };
 const good=sanitizeBatchInventory(source,dates);
 assert.equal(good.status,'inventory_batch_read');
 assert.deepEqual(good.coverage,{
   pagesAttempted:4,pagesVerified:3,pagesFailed:1,domainsRead:2,
   complete:false,reason:'page_error_or_login'
 });
 assert.equal(JSON.stringify(good).includes('DO_NOT_LEAK'),false);
 assert.equal(good.safeToBook,false);
 for(const bad of [
   {...source,coverage:{...source.coverage,complete:true}},
   {...source,coverage:{...source.coverage,pagesVerified:4}},
   {...source,coverage:{...source.coverage,pagesFailed:0}},
   {...source,coverage:{...source.coverage,reason:'all_pages_confirmed'}},
   {...source,coverage:{...source.coverage,pagesAttempted:123}}
 ]){
   const result=sanitizeBatchInventory(bad,dates);
   assert.equal(result.status,'review_required');
   assert.equal(result.bookingAuthorized,false);
 }
});

test('inventory worker receives only five validated planned days, no checkout',async()=>{
 const dates=['2026-11-17','2026-11-18'];
 const calls=[];
 const browser=createBrowser({env:{WESTBAHN_BROWSER_ENABLED:'true',
    WESTBAHN_PYTHON:'/opt/python'},now,execute:runner({
      status:'inventory_batch_read',accountPageReads:0,inventoryComplete:false,
      safeToBook:false,bookingAuthorized:false,days:[]
   },calls)});
 const result=await browser.run('inventory-batch',null,null,dates);
 assert.equal(result.status,'review_required');
 assert.deepEqual(calls[0].args.slice(-3),['inventory-batch','--dates',dates.join(',')]);
 await assert.rejects(browser.run('inventory-batch',null,null,['2026-11-14']));
 await assert.rejects(browser.run('inventory-batch',null,null,[...dates,...dates]));
 assert.equal(calls.length,1);
});

test('offline cloned seat map only reports observed controls, never live availability',()=>{
 const date='2026-11-18';
 const raw={
  status:'seat_preview_offline',
  connection:{date,trainNumber:'1009',displayedPriceCents:0},
  zeroPriceObserved:true,bookingAuthorized:false,liveAvailabilityVerified:false,
  inspection:{seatMapLabel:true,seatControls:[]},
  blockedRequestCount:1,blockedRequests:[{path:'/private/SECRET'}],
  preferredControls:[{seat:'233A',disabled:false,privatePassenger:'SECRET'},
                     {seat:'233D',disabled:true}]
 };
 const x=sanitizeOfflineSeatPreview(raw,date);
 assert.equal(x.status,'offline_seat_map_observed');
 assert.deepEqual(x.preferredSeats,[
   {seat:'233A',observation:'visible_in_offline_copy'},
   {seat:'233D',observation:'disabled_in_offline_copy'},
   {seat:'191D',observation:'unknown'},
   {seat:'182A',observation:'unknown'}
 ]);
 assert.equal(x.liveAvailabilityVerified,false);
 assert.equal(x.bookingAuthorized,false);
 assert.equal(x.canPurchase,false);
 assert.equal(JSON.stringify(x).includes('SECRET'),false);
});

test('fake live availability or ambiguous offline seat controls fail closed',()=>{
 const date='2026-11-18';
 const good={
  status:'seat_preview_offline',connection:{date},
  zeroPriceObserved:true,bookingAuthorized:false,
  liveAvailabilityVerified:false,inspection:{seatMapLabel:true},
  blockedRequestCount:0,
  preferredControls:[{seat:'233A',disabled:false}]
 };
 for(const changes of [
   {liveAvailabilityVerified:true},
   {bookingAuthorized:true},
   {zeroPriceObserved:false},
   {blockedRequestCount:101},
   {inspection:{seatMapLabel:false}},
   {connection:{date:'2026-11-19'}},
   {preferredControls:[{seat:'999A',disabled:false}]},
   {preferredControls:[{seat:'233A',disabled:false},{seat:'233A',disabled:true}]},
   {preferredControls:[{seat:'233D',disabled:'false'}]}
 ]){
   const res=sanitizeOfflineSeatPreview({...good,...changes},date);
   assert.equal(res.status,'review_required');
   assert.equal(res.canPurchase,false);
   assert.equal(res.liveAvailabilityVerified,false);
 }
});

test('seat-preview mode routes only to isolated worker and keeps fail-closed results',async()=>{
 const date='2026-11-18',calls=[];
 const browser=createBrowser({env:{WESTBAHN_BROWSER_ENABLED:'true',
    WESTBAHN_PYTHON:'/opt/python'},now,execute:runner({
     status:'seat_preview_offline',connection:{date},
     zeroPriceObserved:true,bookingAuthorized:false,liveAvailabilityVerified:false,
     inspection:{seatMapLabel:true},blockedRequestCount:0,
     preferredControls:[{seat:'233A',disabled:false}]
   },calls)});
 const result=await browser.run('seat-preview',date);
 assert.equal(result.status,'offline_seat_map_observed');
 assert.deepEqual(calls[0].args.slice(-3),['seat-preview','--date',date]);
 assert.equal(result.canPurchase,false);
});
