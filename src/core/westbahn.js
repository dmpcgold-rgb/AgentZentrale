export const RULES = Object.freeze({origin:'Wien Meidling',destination:'Wiener Neustadt Hbf',departure:'18:22',class:'2+',ticket:'KlimaTicket Österreich',preferred:['233A','233D','191D','182A'],priceCents:0,timezone:'Europe/Vienna'});
export const FIRST_UNRESERVED_DATE='2026-11-17';
export const BOOKING_URL='https://westbahn.at/reservierung/sitzplatz-upgrade/';
export function viennaClock(at=new Date()) {
 const p=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:RULES.timezone,year:'numeric',month:'2-digit',day:'2-digit',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(at).map(x=>[x.type,x.value]));
 return {date:`${p.year}-${p.month}-${p.day}`,time:`${p.hour}:${p.minute}`,weekday:p.weekday};
}
const iso=d=>d.toISOString().slice(0,10);
export function planDates(at=new Date(), months=6) {
 const c=viennaClock(at), start=new Date(`${c.date}T00:00:00Z`), end=new Date(start);
 const day=end.getUTCDate(); end.setUTCDate(1); end.setUTCMonth(end.getUTCMonth()+months); const last=new Date(Date.UTC(end.getUTCFullYear(),end.getUTCMonth()+1,0)).getUTCDate(); end.setUTCDate(Math.min(day,last));
 const out=[]; for(let d=new Date(start); d<=end; d.setUTCDate(d.getUTCDate()+1)) if(iso(d)>=FIRST_UNRESERVED_DATE&&d.getUTCDay()>=1&&d.getUTCDay()<=5&&(iso(d)!==c.date||c.time<RULES.departure)) out.push(iso(d)); return out;
}
export function chooseSeat(seats) {
 if(!Array.isArray(seats))return null;
 const valid=seats.filter(s=>s&&s.available===true&&s.class===RULES.class&&s.groupSize===2&&['opposite-table','offset'].includes(s.layout)&&typeof s.id==='string'&&/^\d{3}[A-Z]$/.test(s.id));
 const rank=s=>{const p=RULES.preferred.indexOf(s.id);return p>=0?p:s.id.startsWith('193')?4:s.layout==='opposite-table'?5:6;};
 return [...valid].sort((a,b)=>rank(a)-rank(b)||a.id.localeCompare(b.id))[0]||null;
}
export function validateQuote(q,date,seat){return !!q&&q.date===date&&q.origin===RULES.origin&&q.destination===RULES.destination&&q.departure===RULES.departure&&q.class===RULES.class&&q.ticket===RULES.ticket&&q.currency==='EUR'&&q.totalCents===0&&q.seat===seat&&typeof q.quoteId==='string'&&q.quoteId.length>0;}
export function confirmedReceipt(r,date,seat){return !!r&&r.confirmed===true&&typeof r.bookingId==='string'&&r.bookingId.trim().length>0&&r.date===date&&r.origin===RULES.origin&&r.destination===RULES.destination&&r.departure===RULES.departure&&r.class===RULES.class&&r.ticket===RULES.ticket&&typeof seat==='string'&&/^\d{3}[A-Z]$/.test(seat)&&r.seat===seat&&r.totalCents===0&&r.currency==='EUR';}
