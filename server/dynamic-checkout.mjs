/** Dynamic WESTbahn intent and independent evidence gates.
 * Neither this module nor its callers should infer that the presence of
 * a quote, a visible basket, or an emailed receipt grants purchase permission.
 */
import {createHash} from 'node:crypto';
import {validateReservationPlan,reservationDates} from './reservation-plan.mjs';
import {RULES} from '../src/core/westbahn.js';

const DATE=/^\d{4}-\d{2}-\d{2}$/;
const TIME=/^(?:[01]\d|2[0-3]):[0-5]\d$/;
const SEAT=/^\d{3}[A-D]$/;
const TRAIN=/^[A-Za-z0-9-]{1,18}$/;
const clean=s=>typeof s==='string'&&s.trim()===s&&s.length>0;
const zero=q=>q?.totalCents===0&&q.currency==='EUR'&&q.quantity===1;
const same=(a,b,fields)=>fields.every(k=>a?.[k]===b?.[k]);
const TRIP_FIELDS=['date','origin','destination','departure','arrival','train','class','ticket','productType','quantity'];

export function createCheckoutIntent({plan,date,connection,at=new Date()}={}){
 const p=validateReservationPlan(plan);
 if(typeof date!=='string'||!DATE.test(date)||
    !reservationDates(p,at).includes(date))
  throw Error('Reisetag liegt außerhalb des aktiven Reservierungsplans.');
 if(!connection||connection.status!=='available'||
    connection.providerVerified!==true||
    connection.source!=='authenticated_westbahn_search'||
    connection.date!==date||connection.origin!==p.origin||
    connection.destination!==p.destination||connection.departure!==p.departure||
    !TIME.test(connection.arrival)||
    !TRAIN.test(connection.train)||
    !clean(connection.connectionId)||
    connection.class!==RULES.class)
  throw Error('Verbindung vom Anbieter nicht vollständig verifiziert.');
 const intent={
  date,origin:p.origin,destination:p.destination,departure:p.departure,
  arrival:connection.arrival,train:connection.train,class:RULES.class,
  ticket:RULES.ticket,productType:RULES.productType,quantity:1,
  connectionId:connection.connectionId
 };
 return Object.freeze(intent);
}

export function chooseVerifiedSeat(intent,inventory){
 if(!intent||!Array.isArray(inventory))return null;
 const eligible=inventory.filter(s=>s?.available===true&&s.class===RULES.class&&
   s.groupSize===2&&['opposite-table','offset'].includes(s.layout)&&
   typeof s.id==='string'&&SEAT.test(s.id));
 const rank=s=>{
  const preferred=RULES.preferred.indexOf(s.id);
  return preferred>=0?preferred:s.id.startsWith('193')?4:
   s.layout==='opposite-table'?5:6;
 };
 return [...eligible].sort((a,b)=>rank(a)-rank(b)||
   a.id.localeCompare(b.id))[0]?.id||null;
}

export function verifyDynamicQuote(intent,seat,quote,{at=new Date()}={}){
 if(!intent||!SEAT.test(seat)||!quote)return false;
 if(!same(intent,quote,TRIP_FIELDS)||
    quote.connectionId!==intent.connectionId||
    quote.seat!==seat||!zero(quote)||!clean(quote.quoteId)||
    quote.source!=='authenticated_westbahn_quote'||
    quote.providerVerified!==true)return false;
 if(typeof quote.issuedAt!=='string'||!Number.isFinite(Date.parse(quote.issuedAt)))
  return false;
 const age=at.getTime()-Date.parse(quote.issuedAt);
 return age>=0&&age<=60_000;
}

export function verifyDynamicReadback(intent,seat,receipt,account){
 if(!intent||!SEAT.test(seat)||!receipt||!account)return false;
 if(!same(intent,receipt,TRIP_FIELDS)||
    !zero(receipt)||receipt.seat!==seat||
    receipt.confirmed!==true||!clean(receipt.bookingId))return false;
 return account.status==='confirmed'&&account.accountVerified===true&&
   account.inventoryComplete===true&&
   account.receiptSource==='provider_account'&&
   same(intent,account.receipt,TRIP_FIELDS)&&
   account.receipt.seat===seat&&account.receipt.confirmed===true&&
   zero(account.receipt)&&
   account.receipt.bookingId===receipt.bookingId;
}

/** Stable one-key-per-journey. Never includes credential or passenger data. */
export function checkoutAttemptKey(intent){
 if(!intent||!clean(intent.connectionId)||!DATE.test(intent.date))
  throw Error('Ungültiger Buchungsauftrag.');
 const canonical=TRIP_FIELDS.map(k=>String(intent[k]??'')).join('|')+
  '|'+intent.connectionId;
 return 'agentzentrale-westbahn-'+createHash('sha256').update(canonical).digest('hex').slice(0,32);
}

/** Never transform a read-only audit into an actionable purchase authorization. */
export function dynamicCheckoutReadiness({intent,seat,quote,cartAudit,existing,
  at=new Date()}={}){
 const checks={
  providerInventoryComplete:existing?.status==='none'&&
    existing?.accountVerified===true&&existing?.inventoryComplete===true,
  validSeat:typeof seat==='string'&&SEAT.test(seat),
  verifiedQuote:verifyDynamicQuote(intent,seat,quote,{at}),
  exactZeroEuroCart:cartAudit?.verified===true&&
    cartAudit?.bookingAuthorized===false&&
    Object.values(cartAudit?.checks||{}).length>=10&&
    Object.values(cartAudit.checks).every(x=>x===true)
 };
 return {checks,allPreflightChecksPassed:Object.values(checks).every(Boolean),
  purchaseAuthorized:false,
  blocker:'dynamic_live_adapter_not_provider_verified'};
}
