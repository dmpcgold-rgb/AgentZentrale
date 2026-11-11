import test from 'node:test';
import assert from 'node:assert/strict';
import {safeTripPreview} from '../trip-preview.mjs';
const date='2026-11-18';
const connection={
 date,origin:'Wien Meidling',destination:'Wiener Neustadt Hbf',
 departure:'18:22',arrival:'18:49',class:'2+',currency:'EUR',
 trainNumber:'1009',displayedPriceCents:0,priceSource:'comfort_control',
 priceStatus:'displayed',priceVerifiedForKlimaTicket:false
};
test('public zero-euro Comfort display is never a verified KlimaTicket checkout',()=>{
 const result=safeTripPreview({date,raw:{
  status:'connection_found',connection,
  rawAccountId:'SHOULD_NOT_LEAK'
 }});
 assert.equal(result.status,'public_connection_found');
 assert.equal(result.displayedComfortCents,0);
 assert.equal(result.klimaTicketPriceVerified,false);
 assert.equal(result.checkoutTotalVerified,false);
 assert.equal(result.seatAvailabilityVerified,false);
 assert.equal(result.accountInventoryVerified,false);
 assert.equal(result.canPurchase,false);
 assert.equal(result.bookingAuthorized,false);
 assert.equal(JSON.stringify(result).includes('SHOULD_NOT_LEAK'),false);
});
test('unknown public price remains null, never coerces to zero',()=>{
 const result=safeTripPreview({date,raw:{
  status:'connection_found',connection:{...connection,displayedPriceCents:null,priceStatus:'not_displayed'}
 }});
 assert.equal(result.status,'public_connection_found');
 assert.equal(result.displayedComfortCents,null);
});
test('invalid route, date, class, currency or train cannot be considered a match',()=>{
 const variants=[
  {date:'2026-11-19'}, {origin:'Salzburg Hbf'}, {destination:'Wien Meidling'},
  {departure:'18:23'}, {class:'1'}, {currency:'USD'},
  {trainNumber:'abc'}, {arrival:'invalid'}
 ];
 for(const changes of variants){
  const result=safeTripPreview({date,raw:{
    status:'connection_found',connection:{...connection,...changes}
  }});
  assert.equal(result.status,'review_required');
  assert.equal(result.displayedComfortCents,null);
  assert.equal(result.canPurchase,false);
 }
});
test('existing recorded day blocks public preview even if fake connection says zero',()=>{
 for(const status of ['confirmed','existing_verified','user_reported','uncertain','booking','blocked']){
  const result=safeTripPreview({date,raw:{status:'connection_found',connection},
    ledgerRows:[{date,status,seat:'191D'}]});
  assert.equal(result.status,'existing_ledger_entry');
  assert.equal(result.displayedComfortCents,null);
  assert.equal(result.canPurchase,false);
 }
});
test('forged public zero price without exact control source is rejected',()=>{
 for(const changes of [
  {priceSource:'marketing_banner'},
  {priceStatus:'ambiguous'},
  {displayedPriceCents:-1},
  {displayedPriceCents:'0'}
 ]){
  const result=safeTripPreview({date,raw:{
    status:'connection_found',connection:{...connection,...changes}
  }});
  assert.equal(result.status,'public_connection_found');
  assert.equal(result.displayedComfortCents,null);
 }
});
