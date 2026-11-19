import {RULES,planDates} from '../src/core/westbahn.js';
import {DEFAULT_RESERVATION_PLAN,isLegacyReservationPlan,nextReservationBatch} from './reservation-plan.mjs';

// Read-only operational view. Never equate absence from a paginated browser
// view with a confirmed missing reservation.
export function bookingReadiness({westbahn,review,now=new Date(),plan=DEFAULT_RESERVATION_PLAN}={}){
 const ledger=westbahn.status();
 const run=review?.status()?.lastRun??null;
 const lastRows=Array.isArray(run?.days)?run.days:[];
 const rows=Array.isArray(ledger.rows)?ledger.rows:[];
 const nextFive=nextReservationBatch(plan,{at:now});
 const days=nextFive.map(date=>{
  const entry=rows.find(x=>x.date===date);
  const observed=lastRows.find(x=>x.date===date);
  let status='inventory_unverified';
  if(['existing_verified','confirmed'].includes(entry?.status))status='protected_existing';
  else if(entry?.status==='user_reported')status='reported_existing';
  else if(['booking','uncertain'].includes(entry?.status))status='checkout_needs_review';
  else if(observed?.status==='detail_verified')status='verified_ticket_needs_ledger_check';
  else if(['possible_existing','visible_year_verified'].includes(observed?.status))status='possible_existing';
  else if(entry?.status==='blocked')status='manual_review_required';
  return {date,status,seat:typeof entry?.seat==='string'?entry.seat:null,
          bookable:false};
 });
 return {
  status:'checkout_not_ready',days,
  itinerary:{origin:plan.origin,destination:plan.destination,departure:plan.departure,
    weekdays:[...plan.weekdays],horizon:plan.horizon,
    bookingWindowStart:plan.bookingWindowStart,bookingWindowEnd:plan.bookingWindowEnd},
  legacyItineraryCompatible:isLegacyReservationPlan(plan),
  dynamicAdapterContractReady:ledger.dynamicProviderVerified===true,
  preferredSeats:RULES.preferred.slice(0,2),
  alternativeSeats:RULES.preferred.slice(2),
  requiredDeparture:plan.departure,
  requiredClass:RULES.class,
  maxTotalCents:0,
  automaticBookingEnabled:ledger.automatic===true,
  fullInventoryVerified:false,
  liveCheckoutAdapterVerified:false,
  currentQuoteVerified:false,
  providerReceiptReadbackVerified:false,
  canPurchase:false,
  blockers:[
   ...(!isLegacyReservationPlan(plan)&&ledger.dynamicProviderVerified!==true?['custom_itinerary_provider_not_verified']:[]),
   'complete_authenticated_inventory',
   ...(!ledger.providerConnected?['real_provider_checkout_adapter']:[]),
   'fresh_exact_zero_euro_checkout',
   'independent_matching_account_receipt'
  ]
 };
}
