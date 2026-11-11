import test from 'node:test';
import assert from 'node:assert/strict';
import {createAgentHandler} from '../index.mjs';

const token='PRIVATE-SINGLE-USER-TEST-TOKEN-123456789';
const date='2026-11-17',seat='191D';
const weekDates=['2026-11-17','2026-11-18','2026-11-19','2026-11-20','2026-11-23'];
// The real server always requests all five dates, even if a fixture
// focuses only on one or two candidate tickets.
const withFiveDates=b=>({
 accountPageReads:4,...b,
 days:[...b.days,...weekDates.slice(b.days.length).map(date=>({
  date,status:'review_required',seats:[],dateVerified:false,
  detailVerified:false,potentialDuplicate:false,safeToBook:false
 }))]
});

async function request(handler, {path='/westbahn/browser/audit-ticket',body={date,seat},
 method='POST',authorization='Bearer '+token}={}){
 const req={
  method,url:path,headers:{authorization},
  async *[Symbol.asyncIterator](){yield Buffer.from(JSON.stringify(body));}
 };
 const res={
  status:0,payload:null,
  writeHead(code){this.status=code;},
  end(raw){this.payload=JSON.parse(raw);}
 };
 await handler(req,res);
 return {status:res.status,body:res.payload};
}

test('authenticated ticket-audit route only invokes read-only browser mode',async()=>{
 const calls=[];
 const expected={status:'existing_ticket_verified',date,seat,
  inventoryComplete:false,safeToBook:false,bookingAuthorized:false,
  confirmationVerified:false,
  checks:{detailRead:true,yearVerified:true,seatMatched:true,
          tripMatched:true,referenceVisible:true,dateExplicit:true}};
 const protectedRows=[];
 const browser={status:()=>({enabled:true,liveBooking:false}),
   async run(...args){calls.push(args);return expected;}};
 const westbahn={run(){throw Error('must not book')},
    recordVerifiedExisting(...args){protectedRows.push(args);}};
 const handler=createAgentHandler({
   env:{AGENTZENTRALE_ACCESS_TOKEN:token},browser,westbahn
 });
 const result=await request(handler);
 assert.equal(result.status,200);
 assert.deepEqual(result.body,{...expected,ledgerProtected:true});
 assert.deepEqual(calls,[['ticket-detail-check',date,seat]]);
 assert.deepEqual(protectedRows,[[date,seat]]);
});

test('audit endpoint requires auth and complete date/seat values',async()=>{
 const calls=[];
 const handler=createAgentHandler({
  env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  browser:{async run(...args){calls.push(args);return {status:'review_required'}}}
 });
 const unauth=await request(handler,{authorization:'Bearer wrong'});
 assert.equal(unauth.status,401);
 const incomplete=await request(handler,{body:{date}});
 assert.equal(incomplete.status,400);
 assert.deepEqual(calls,[]);
});

test('unverified provider evidence must never change the booking ledger',async()=>{
 const recorded=[];
 const browser={async run(){return {status:'review_required',date,seat,
  inventoryComplete:false,safeToBook:false,bookingAuthorized:false};}};
 const westbahn={recordVerifiedExisting(...args){recorded.push(args);},
  run(){throw Error('should not book')}};
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},browser,westbahn});
 const res=await request(handler);
 assert.equal(res.status,200);
 assert.equal(res.body.ledgerProtected,false);
 assert.deepEqual(recorded,[]);
});

test('read-only browser errors never initiate a booking or claim success',async()=>{
 const handler=createAgentHandler({
  env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  browser:{async run(){throw Error('Ticketdaten nicht eindeutig')}},
  westbahn:{run(){throw Error('must not invoke booking')}}
 });
 const result=await request(handler);
 assert.equal(result.status,409);
 assert.equal(result.body.error,'Ticketdaten nicht eindeutig');
});


test('authenticated five-day audit derives dates on server and cannot call checkout',async()=>{
 const calls=[];
 const browser={async run(...args){calls.push(args);
   return {status:'inventory_batch_read',days:[],inventoryComplete:false,
      safeToBook:false,bookingAuthorized:false};}};
 const westbahn={run(){throw Error('must never buy')}};
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  now:()=>Date.parse('2026-11-11T12:00:00Z'),browser,westbahn});
 const res=await request(handler,{path:'/westbahn/browser/audit-week',body:{}});
 assert.equal(res.status,200);
 assert.equal(res.body.bookingAuthorized,false);
 assert.equal(calls.length,1);
 assert.equal(calls[0][0],'inventory-batch');
 assert.equal(calls[0][3].length,5);
 assert.equal(calls[0][3][0],'2026-11-17');
});

test('five-day audit persists only uniquely verified existing tickets',async()=>{
 const days=['2026-11-17','2026-11-18','2026-11-19'];
 const calls=[];
 const batch={status:'inventory_batch_read',inventoryComplete:false,
   safeToBook:false,bookingAuthorized:false,days:[
    {date:days[0],status:'detail_verified',seats:['191D'],
      dateVerified:true,detailVerified:true,potentialDuplicate:true,safeToBook:false},
    {date:days[1],status:'possible_existing',seats:['233A'],
      dateVerified:false,detailVerified:false,potentialDuplicate:true,safeToBook:false},
    {date:days[2],status:'review_required',seats:[],
      dateVerified:false,detailVerified:false,potentialDuplicate:false,safeToBook:false}
  ]};
 const westbahn={
   recordVerifiedExisting(date,seat){
     calls.push([date,seat]);
     return {rows:[{date,seat,status:'existing_verified'}]};
   },
   run(){throw Error('must never book')}
 };
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
   now:()=>Date.parse('2026-11-11T12:00:00Z'),
   browser:{async run(){return withFiveDates(batch);}},westbahn});
 const res=await request(handler,{path:'/westbahn/browser/audit-week',body:{}});
 assert.equal(res.status,200);
 assert.deepEqual(calls,[[days[0],'191D']]);
 assert.deepEqual(res.body.ledgerProtectedDates,[days[0]]);
 assert.deepEqual(res.body.ledgerReviewDates,[]);
 assert.equal(res.body.safeToBook,false);
 assert.equal(res.body.bookingAuthorized,false);
});

test('unverified or conflicting weekly ticket never modifies protected ledger',async()=>{
 const calls=[];
 const days=['2026-11-17','2026-11-18'];
 const batch={status:'inventory_batch_read',inventoryComplete:false,
    safeToBook:false,bookingAuthorized:false,days:[
    {date:days[0],status:'detail_verified',seats:['191D'],dateVerified:true,
      detailVerified:true,potentialDuplicate:true,safeToBook:false},
    {date:days[1],status:'review_required',seats:[],dateVerified:false,
      detailVerified:false,potentialDuplicate:false,safeToBook:false}
 ]};
 const westbahn={recordVerifiedExisting(date,seat){
   calls.push([date,seat]);throw Error('Conflicting existing seat');
 },run(){throw Error('must not book')}};
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
   now:()=>Date.parse('2026-11-11T12:00:00Z'),
   browser:{async run(){return withFiveDates(batch);}},westbahn});
 const res=await request(handler,{path:'/westbahn/browser/audit-week',body:{}});
 assert.equal(res.status,200);
 assert.deepEqual(res.body.ledgerProtectedDates,[]);
 assert.deepEqual(res.body.ledgerReviewDates,[days[0]]);
 assert.deepEqual(calls,[[days[0],'191D']]);
 assert.equal(res.body.bookingAuthorized,false);
});

test('uncertain checkout remains manual review despite matching visible ticket',async()=>{
 const days=['2026-11-17'];
 const batch={status:'inventory_batch_read',inventoryComplete:false,
    safeToBook:false,bookingAuthorized:false,days:[
    {date:days[0],status:'detail_verified',seats:['191D'],
      dateVerified:true,detailVerified:true,potentialDuplicate:true,safeToBook:false}
 ]};
 const westbahn={recordVerifiedExisting(date,seat){
    return {rows:[{date,seat,status:'uncertain'}]};
 },run(){throw Error('must not book')}};
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
    now:()=>Date.parse('2026-11-11T12:00:00Z'),
    browser:{async run(){return withFiveDates(batch);}},westbahn});
 const res=await request(handler,{path:'/westbahn/browser/audit-week',body:{}});
 assert.equal(res.status,200);
 assert.deepEqual(res.body.ledgerProtectedDates,[]);
 assert.deepEqual(res.body.ledgerReviewDates,[days[0]]);
 assert.equal(res.body.bookingAuthorized,false);
});

test('falsified positive data without fail-closed flags never locks ticket',async()=>{
 const calls=[];
 const batch={status:'inventory_batch_read',inventoryComplete:true,
    safeToBook:false,bookingAuthorized:false,days:[
    {date:'2026-11-17',status:'detail_verified',seats:['191D'],
      detailVerified:true,dateVerified:true,potentialDuplicate:true,safeToBook:false}
 ]};
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
    now:()=>Date.parse('2026-11-11T12:00:00Z'),
    browser:{async run(){return withFiveDates(batch);}},
    westbahn:{recordVerifiedExisting(...args){calls.push(args);},
      run(){throw Error('must not book')}}});
 const res=await request(handler,{path:'/westbahn/browser/audit-week',body:{}});
 assert.equal(res.status,200);
 assert.deepEqual(res.body.ledgerProtectedDates,[]);
 assert.deepEqual(calls,[]);
});

test('five-day audit rejects unauthenticated request without opening browser',async()=>{
 const calls=[];
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  browser:{async run(...args){calls.push(args);return {};}}});
 const res=await request(handler,{path:'/westbahn/browser/audit-week',authorization:'Bearer invalid'});
 assert.equal(res.status,401);
 assert.equal(calls.length,0);
});

test('five-day audit browser error never claims a complete inventory',async()=>{
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  browser:{async run(){throw Error('Browser gesperrt');}}});
 const res=await request(handler,{path:'/westbahn/browser/audit-week',body:{}});
 assert.equal(res.status,409);
 assert.equal(res.body.error,'Browser gesperrt');
});


test('read-only scheduler status and readiness endpoints require authentication',async()=>{
 const now=()=>Date.parse('2026-11-11T13:00:00Z');
 const review={status:()=>({enabled:true,running:false,lastSchedule:'2026-11-09',
  lastRun:{status:'inventory_batch_read',days:[]},purchaseEnabled:false,
  inventoryComplete:false})};
 const westbahn={status:()=>({rows:[
  {date:'2026-11-17',status:'existing_verified',seat:'191D'}
 ]})};
 const handler=createAgentHandler({
  env:{AGENTZENTRALE_ACCESS_TOKEN:token},now,review,westbahn
 });
 const status=await request(handler,{method:'GET',path:'/westbahn/review-status'});
 assert.equal(status.status,200);
 assert.equal(status.body.enabled,true);
 assert.equal(status.body.purchaseEnabled,false);
 const readiness=await request(handler,{method:'GET',path:'/westbahn/readiness'});
 assert.equal(readiness.status,200);
 assert.equal(readiness.body.status,'checkout_not_ready');
 assert.equal(readiness.body.days[0].status,'protected_existing');
 assert.deepEqual(readiness.body.preferredSeats,['233A','233D']);
 assert.equal(readiness.body.canPurchase,false);
 const unauthorized=await request(handler,{method:'GET',
   path:'/westbahn/readiness',authorization:'Bearer incorrect'});
 assert.equal(unauthorized.status,401);
});

test('manual five-day review uses scheduler runner instead of separate booking path',async()=>{
 const calls=[];
 const review={async run(){calls.push('review');
  return {status:'inventory_batch_read',days:[],inventoryComplete:false,
    safeToBook:false,bookingAuthorized:false,ledgerProtectedDates:[]};},
  status:()=>({enabled:true})};
 const browser={async run(){throw Error('must use scheduler review')}};
 const westbahn={run(){throw Error('must never initiate checkout')}};
 const handler=createAgentHandler({
  env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  now:()=>Date.parse('2026-11-11T13:00:00Z'),review,browser,westbahn
 });
 const response=await request(handler,{path:'/westbahn/browser/audit-week',body:{}});
 assert.equal(response.status,200);
 assert.equal(response.body.bookingAuthorized,false);
 assert.deepEqual(calls,['review']);
});


test('public trip preview only reads one supported connection and redacts provider fields',async()=>{
 const calls=[];
 const browser={async run(...args){
   calls.push(args);
   return {status:'connection_found',accountReference:'SECRET-ACCOUNT',
     connection:{date:'2026-11-18',origin:'Wien Meidling',
      destination:'Wiener Neustadt Hbf',departure:'18:22',arrival:'18:49',
      class:'2+',currency:'EUR',trainNumber:'1009',displayedPriceCents:0,
      priceSource:'comfort_control',priceStatus:'displayed'}};
 }};
 const westbahn={status:()=>({rows:[]}),
   run(){throw Error('never buy')}};
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
   now:()=>Date.parse('2026-11-11T12:00:00Z'),browser,westbahn});
 const res=await request(handler,{path:'/westbahn/browser/preview-trip',
   body:{date:'2026-11-18'}});
 assert.equal(res.status,200);
 assert.deepEqual(calls,[['prepare','2026-11-18']]);
 assert.equal(res.body.status,'public_connection_found');
 assert.equal(res.body.displayedComfortCents,0);
 assert.equal(res.body.canPurchase,false);
 assert.equal(res.body.klimaTicketPriceVerified,false);
 assert.equal(res.body.accountInventoryVerified,false);
 assert.equal(JSON.stringify(res.body).includes('SECRET-ACCOUNT'),false);
});

test('recorded day does not open preview browser or claim a free seat',async()=>{
 const calls=[];
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
   now:()=>Date.parse('2026-11-11T12:00:00Z'),
   browser:{async run(...args){calls.push(args);return {};}},
   westbahn:{status:()=>({rows:[{date:'2026-11-17',status:'existing_verified',seat:'191D'}]})}});
 const res=await request(handler,{path:'/westbahn/browser/preview-trip',
   body:{date:'2026-11-17'}});
 assert.equal(res.status,200);
 assert.equal(res.body.status,'existing_ledger_entry');
 assert.equal(res.body.canPurchase,false);
 assert.deepEqual(calls,[]);
});

test('public preview requires authentication and an allowed planned day',async()=>{
 const calls=[];
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  now:()=>Date.parse('2026-11-11T12:00:00Z'),
  westbahn:{status:()=>({rows:[]})},
  browser:{async run(...args){calls.push(args);return {};}}});
 const rejected=await request(handler,{path:'/westbahn/browser/preview-trip',
   body:{date:'2026-11-18'},authorization:'Bearer invalid'});
 assert.equal(rejected.status,401);
 const invalid=await request(handler,{path:'/westbahn/browser/preview-trip',
   body:{date:'2026-11-14'}});
 assert.equal(invalid.status,400);
 assert.deepEqual(calls,[]);
});

test('public preview browser error never implies checkout readiness',async()=>{
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  now:()=>Date.parse('2026-11-11T12:00:00Z'),
  westbahn:{status:()=>({rows:[]})},
  browser:{async run(){throw Error('provider unavailable');}}});
 const res=await request(handler,{path:'/westbahn/browser/preview-trip',
   body:{date:'2026-11-18'}});
 assert.equal(res.status,200);
 assert.equal(res.body.status,'review_required');
 assert.equal(res.body.displayedComfortCents,null);
 assert.equal(res.body.canPurchase,false);
 assert.equal(JSON.stringify(res.body).includes('provider unavailable'),false);
});

test('isolated seat map API only invokes preview mode and never claims bookability',async()=>{
 const seen=[];
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  now:()=>Date.parse('2026-11-11T12:00:00Z'),
  westbahn:{status:()=>({rows:[]}),run(){throw Error('no checkout')}},
  browser:{async run(...args){seen.push(args);return {
    date:'2026-11-18',status:'offline_seat_map_observed',
    preferredSeats:[{seat:'233A',observation:'visible_in_offline_copy'}],
    liveAvailabilityVerified:false,seatSelectionConfirmed:false,
    bookingAuthorized:false,canPurchase:false
  };}}
 });
 const res=await request(handler,{path:'/westbahn/browser/seat-preview',body:{date:'2026-11-18'}});
 assert.equal(res.status,200);
 assert.deepEqual(seen,[['seat-preview','2026-11-18']]);
 assert.equal(res.body.canPurchase,false);
 assert.equal(res.body.liveAvailabilityVerified,false);
});

test('known booked day cannot be opened in isolated preview',async()=>{
 const seen=[];
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  now:()=>Date.parse('2026-11-11T12:00:00Z'),
  westbahn:{status:()=>({rows:[{date:'2026-11-17',status:'existing_verified',seat:'191D'}]})},
  browser:{async run(...args){seen.push(args);return {};}}
 });
 const res=await request(handler,{path:'/westbahn/browser/seat-preview',body:{date:'2026-11-17'}});
 assert.equal(res.status,200);
 assert.equal(res.body.status,'existing_ledger_entry');
 assert.deepEqual(seen,[]);
});
test('seat-preview rejects dates outside plan without launching Chromium',async()=>{
 const seen=[];
 const handler=createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:token},
  now:()=>Date.parse('2026-11-11T12:00:00Z'),
  westbahn:{status:()=>({rows:[]})},
  browser:{async run(...args){seen.push(args);return {};}}
 });
 const res=await request(handler,{path:'/westbahn/browser/seat-preview',body:{date:'2026-11-15'}});
 assert.equal(res.status,400);
 assert.deepEqual(seen,[]);
});
