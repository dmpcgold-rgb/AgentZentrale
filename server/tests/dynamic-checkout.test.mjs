import test from 'node:test';
import assert from 'node:assert/strict';
import {DEFAULT_RESERVATION_PLAN} from '../reservation-plan.mjs';
import {RULES} from '../../src/core/westbahn.js';
import {createCheckoutIntent,chooseVerifiedSeat,verifyDynamicQuote,
 verifyDynamicReadback,checkoutAttemptKey,dynamicCheckoutReadiness} from '../dynamic-checkout.mjs';

const at=new Date('2026-11-23T06:00:00Z');
const date='2026-11-24';
const connection={status:'available',source:'authenticated_westbahn_search',
 providerVerified:true,date,origin:DEFAULT_RESERVATION_PLAN.origin,
 destination:DEFAULT_RESERVATION_PLAN.destination,
 departure:'18:22',arrival:'18:49',train:'1009',class:'2+',
 connectionId:'trip-1009-24'};
const intent=()=>createCheckoutIntent({plan:DEFAULT_RESERVATION_PLAN,
 date,connection,at});
const quote=()=>({...intent(),connectionId:connection.connectionId,
 seat:'233A',quoteId:'q-1',issuedAt:at.toISOString(),
 totalCents:0,currency:'EUR',source:'authenticated_westbahn_quote',
 providerVerified:true});
const receipt=()=>({...intent(),seat:'233A',bookingId:'ticket-1',
 confirmed:true,totalCents:0,currency:'EUR'});
const cart=()=>({verified:true,bookingAuthorized:false,
 checks:Object.fromEntries(Array.from({length:11},(_,i)=>['check'+i,true]))});

test('dynamic intent preserves provider verified train and arrival, never guesses from departure',()=>{
 const it=intent();
 assert.equal(it.arrival,'18:49');assert.equal(it.train,'1009');
 assert.ok(Object.isFrozen(it));
 for(const patch of [{providerVerified:false},{source:'public_webpage'},
   {departure:'17:22'},{origin:'Wien Westbahnhof'},{arrival:''},
   {train:''},{connectionId:''},{class:'1'}]){
  assert.throws(()=>createCheckoutIntent({plan:DEFAULT_RESERVATION_PLAN,
   date,connection:{...connection,...patch},at}));
 }
 assert.throws(()=>createCheckoutIntent({plan:DEFAULT_RESERVATION_PLAN,
   date:'2027-01-01',connection,at}));
});

test('verified seats retain priority and reject four-seat groups',()=>{
 const inventory=[
  {id:'233D',available:true,class:'2+',layout:'offset',groupSize:2},
  {id:'233A',available:true,class:'2+',layout:'opposite-table',groupSize:2},
  {id:'191D',available:true,class:'2+',layout:'opposite-table',groupSize:2},
  {id:'232A',available:true,class:'2+',layout:'opposite-table',groupSize:4}
 ];
 assert.equal(chooseVerifiedSeat(intent(),inventory),'233A');
 assert.equal(chooseVerifiedSeat(intent(),inventory.slice(0,1)),'233D');
 assert.equal(chooseVerifiedSeat(intent(),inventory.slice(3)),null);
});

test('dynamic quote requires freshly verified exact-zero train, route, seat and product',()=>{
 assert.equal(verifyDynamicQuote(intent(),'233A',quote(),{at}),true);
 for(const patch of [{totalCents:1},{currency:'USD'},{seat:'233D'},
  {arrival:'18:48'},{train:'1010'},{origin:'Wien Westbahnhof'},
  {quantity:2},{productType:'ticket'},{providerVerified:false},
  {source:'public_webpage'},{connectionId:'another'},
  {issuedAt:'2026-11-23T05:58:00Z'}]){
  assert.equal(verifyDynamicQuote(intent(),'233A',{...quote(),...patch},{at}),false,
   JSON.stringify(patch));
 }
});

test('post-purchase readback requires independent matching receipt in provider account',()=>{
 const confirmation=receipt();
 const account={status:'confirmed',accountVerified:true,inventoryComplete:true,
  receiptSource:'provider_account',receipt:confirmation};
 assert.equal(verifyDynamicReadback(intent(),'233A',confirmation,account),true);
 assert.equal(verifyDynamicReadback(intent(),'233A',confirmation,
  {...account,inventoryComplete:false}),false);
 assert.equal(verifyDynamicReadback(intent(),'233A',confirmation,
  {...account,receiptSource:'email'}),false);
 assert.equal(verifyDynamicReadback(intent(),'233A',confirmation,
  {...account,receipt:{...confirmation,bookingId:'other'}}),false);
 assert.equal(verifyDynamicReadback(intent(),'233A',
  {...confirmation,totalCents:1},account),false);
 assert.equal(verifyDynamicReadback(intent(),'233A',confirmation,
  {...account,receipt:{...confirmation,train:'1010'}}),false);
});

test('same trip gives stable one-shot attempt identifier with no private data',()=>{
 const a=checkoutAttemptKey(intent());
 assert.equal(a,checkoutAttemptKey(intent()));
 assert.match(a,/^agentzentrale-westbahn-[a-f0-9]{32}$/);
 assert.notEqual(a,checkoutAttemptKey({...intent(),connectionId:'other'}));
});

test('preflight read-only even when every quote and cart check passes',()=>{
 const base={intent:intent(),seat:'233A',quote:quote(),cartAudit:cart(),
  existing:{status:'none',accountVerified:true,inventoryComplete:true},at};
 const result=dynamicCheckoutReadiness(base);
 assert.equal(result.allPreflightChecksPassed,true);
 assert.equal(result.purchaseAuthorized,false);
 for(const diff of [{existing:{status:'none',accountVerified:true,inventoryComplete:false}},
  {quote:{...quote(),totalCents:99}},{cartAudit:{...cart(),bookingAuthorized:true}},
  {cartAudit:{...cart(),checks:{...cart().checks,check0:false}}}]){
  const outcome=dynamicCheckoutReadiness({...base,...diff});
  assert.equal(outcome.allPreflightChecksPassed,false);
  assert.equal(outcome.purchaseAuthorized,false);
 }
});
