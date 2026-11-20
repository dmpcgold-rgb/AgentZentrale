import test from 'node:test';
import assert from 'node:assert/strict';
import {createWestbahn,dynamicAdapterReady} from '../westbahn.mjs';
import {DEFAULT_RESERVATION_PLAN} from '../reservation-plan.mjs';
import {RULES} from '../../src/core/westbahn.js';

const now=()=>new Date('2026-11-23T06:00:00Z');
const plan={...DEFAULT_RESERVATION_PLAN,origin:'Wien Westbahnhof',
 destination:'Salzburg Hbf',departure:'10:30',weekdays:[2],horizon:'1w'};
const day='2026-11-24';
const seats=[{id:'233D',available:true,class:'2+',groupSize:2,layout:'offset'},
 {id:'233A',available:true,class:'2+',groupSize:2,layout:'opposite-table'}];
const capabilities={dynamicItineraries:true,authenticatedFullInventory:true,
 freshZeroEuroQuotes:true,checkoutDomAudit:true,durableIdempotency:true,
 independentAccountReadback:true};
const audit={verified:true,bookingAuthorized:false,
 checks:Object.fromEntries(Array.from({length:11},(_,i)=>['check'+i,true]))};
function fixture({inventoryComplete=true,price=0,misroute=false,
 auditApproved=true,throwBooking=false,readbackMatch=true,existingConflict=false}={}){
 let count=0, accountReads=0, bookings=[];
 const trip={date:day,origin:misroute?'Wrong City':plan.origin,
  destination:plan.destination,departure:plan.departure,arrival:'12:40',
  train:'1234',class:RULES.class,ticket:RULES.ticket,
  productType:RULES.productType,quantity:1,connectionId:'verified-1234'};
 const receipt={...trip,seat:'233A',bookingId:'PROVIDER-1',
  confirmed:true,currency:'EUR',totalCents:0};
 const adapter={
  capabilities:{...capabilities},
  get count(){return count},
  get reads(){return accountReads},
  get bookings(){return bookings},
  existing:async ()=>{
   accountReads++;
   if(existingConflict&&!count){
    return {status:'confirmed',accountVerified:true,inventoryComplete:true,
     receiptSource:'provider_account',receipt:{...receipt,origin:'Wrong City'}};
   }
   if(count){
    return {status:'confirmed',accountVerified:true,inventoryComplete:true,
     receiptSource:'provider_account',
     receipt:readbackMatch?receipt:{...receipt,bookingId:'OTHER'}};
   }
   return {status:'none',accountVerified:true,inventoryComplete};
  },
  search:async ()=>({status:'available',source:'authenticated_westbahn_search',
    providerVerified:true,...trip,seats}),
  quote:async ({seat})=>({...trip,seat,quoteId:'Q-1',
    issuedAt:now().toISOString(),currency:'EUR',totalCents:price,
    source:'authenticated_westbahn_quote',providerVerified:true}),
  audit:async ()=>auditApproved?audit:{...audit,verified:false},
  book:async (args)=>{
   bookings.push(args);
   count++;
   if(throwBooking)throw new Error('network interrupted');
   return receipt;
  }
 };
 return adapter;
}

test('custom itinerary cannot enable legacy, incomplete or read-only adapter',()=>{
 const a=createWestbahn({getPlan:()=>plan,adapter:{
  existing:async()=>({status:'none'})},now});
 assert.equal(a.status().dynamicProviderVerified,false);
 assert.throws(()=>a.setEnabled(true),/verifizierten Buchungsadapter/);
 assert.equal(dynamicAdapterReady(fixture()),true);
 const b=fixture();delete b.capabilities.durableIdempotency;
 assert.equal(dynamicAdapterReady(b),false);
});

test('dynamic itinerary must verify inventory, fresh quote, DOM and account receipt',async()=>{
 const adapter=fixture();
 const a=createWestbahn({getPlan:()=>plan,adapter,now});
 assert.equal(a.setEnabled(true).automatic,true);
 await a.run();
 assert.equal(adapter.count,1);
 assert.equal(adapter.bookings[0].seat,'233A');
 assert.equal(adapter.bookings[0].maxTotalCents,0);
 assert.match(adapter.bookings[0].idempotencyKey,/^agentzentrale-westbahn-[0-9a-f]{32}$/);
 assert.equal(a.status().rows[0].date,day);
 assert.equal(a.status().rows[0].status,'confirmed');
 await a.run();
 assert.equal(adapter.count,1,'confirmed journey never booked twice');
});

test('custom journey never books on incomplete inventory, wrong route, paid quote or missing cart audit',async()=>{
 for(const changes of [{inventoryComplete:false},{misroute:true},{price:1},{auditApproved:false}]){
  const adapter=fixture(changes);
  const a=createWestbahn({getPlan:()=>plan,adapter,now});
  await a.run();
  assert.equal(adapter.count,0,JSON.stringify(changes));
  assert.equal(a.status().rows[0].status,'blocked');
 }
});

test('uncertain checkout and missing independent readback remain locked',async()=>{
 for(const changes of [{throwBooking:true},{readbackMatch:false}]){
  const adapter=fixture(changes);
  const a=createWestbahn({getPlan:()=>plan,adapter,now});
  await a.run();
  assert.equal(adapter.count,1);
  assert.equal(a.status().rows[0].status,'uncertain');
  await a.run();
  assert.equal(adapter.count,1);
 }
});

test('contradictory positive existing ticket is permanently protected against later missing inventory',async()=>{
 const adapter=fixture({existingConflict:true});
 const a=createWestbahn({getPlan:()=>plan,adapter,now});
 await a.run();
 assert.equal(adapter.count,0);
 assert.equal(a.status().rows[0].status,'uncertain');
 await a.run();
 assert.equal(adapter.count,0);
 assert.equal(a.status().rows[0].status,'uncertain');
});
