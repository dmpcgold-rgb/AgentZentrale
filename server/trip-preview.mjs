import {RULES,planDates} from '../src/core/westbahn.js';

// Public timetable/Comfort-class preview only. No purchase, cart, or seat map.
// Positive account ticket evidence must be checked separately.
export function safeTripPreview({date,raw,ledgerRows=[]}={}){
 const base={date,origin:RULES.origin,destination:RULES.destination,
   departure:RULES.departure,travelClass:RULES.class,
   priceKind:'public_comfort_display_only',displayedComfortCents:null,
   currency:'EUR',trainNumber:null,arrival:null,status:'review_required',
   accountInventoryVerified:false,seatAvailabilityVerified:false,
   klimaTicketPriceVerified:false,checkoutTotalVerified:false,
   bookingAuthorized:false,canPurchase:false};
 if(typeof date!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(date))return base;
 if(Array.isArray(ledgerRows)&&ledgerRows.some(r=>r?.date===date))
   return {...base,status:'existing_ledger_entry'};
 if(!raw||raw.status!=='connection_found'||!raw.connection||
    typeof raw.connection!=='object')return base;
 const c=raw.connection;
 const valid=c.date===date && c.origin===RULES.origin &&
   c.destination===RULES.destination && c.departure===RULES.departure &&
   c.class===RULES.class && c.currency==='EUR' &&
   /^\d{3,5}$/.test(String(c.trainNumber||'')) &&
   /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(String(c.arrival||''));
 if(!valid)return base;
 const displayed=Number.isSafeInteger(c.displayedPriceCents) &&
   c.displayedPriceCents>=0&&c.displayedPriceCents<=100000 &&
   c.priceSource==='comfort_control' && c.priceStatus==='displayed'
     ?c.displayedPriceCents:null;
 return {...base,status:'public_connection_found',
   trainNumber:String(c.trainNumber),arrival:c.arrival,
   displayedComfortCents:displayed};
}
