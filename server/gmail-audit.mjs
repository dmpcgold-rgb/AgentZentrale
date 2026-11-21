/** Server-side read-only Gmail evidence. Never treat an empty search as proof that no booking exists. */
import {RULES} from '../src/core/westbahn.js';

const gmail='https://gmail.googleapis.com/gmail/v1/users/me';
const DATE=/^\d{4}-\d{2}-\d{2}$/;
function decodeBase64Url(value){
 return Buffer.from(value.replace(/-/g,'+').replace(/_/g,'/'),'base64').toString('utf8');
}
function flatten(part,parts=[]){
 if(!part||typeof part!=='object')return parts;
 if(part.mimeType==='text/plain'&&part.body?.data)parts.push(decodeBase64Url(part.body.data));
 for(const child of part.parts||[])flatten(child,parts);
 return parts;
}
export function evaluateBookingEmail(messages,date,{searchComplete=false}={}){
 if(!DATE.test(date))throw Error('Invalid travel date');
 const [y,m,d]=date.split('-');
 const monthName=['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'][Number(m)-1];
 const dateWords=[date,`${d}.${m}.${y}`,`${Number(d)}.${Number(m)}.${y}`];
 const spacedDate=new RegExp(String.raw`(?:^|\s)${Number(d)}\s+${monthName}(?:\s|$)`,'i');
 const matches=(messages||[]).filter(msg=>{
  const text=[msg.subject,msg.snippet,msg.body].filter(Boolean).join(' ');
  const travel=dateWords.some(x=>text.includes(x))||spacedDate.test(text);
  const route=/(?:Wien|W[.])\s*Meidling/i.test(text)&&/(?:Wiener|Wr[.])\s*Neustadt/i.test(text);
  const isReservation=/reservier|buchungsbestätig|booking confirmation|comfort class|sitzplatz|Westbahn-Ticket/i.test(text);
  return travel && route && isReservation;
 });
 return {status:matches.length?'possible_existing':'no_matching_email_observed',
   possibleExisting:matches.length>0,mailboxComplete:searchComplete,searchComplete,absenceProven:false,
   bookingAuthorized:false,matchingCount:matches.length};
}
export function createGmailAudit({clientId,clientSecret,refreshToken,fetchImpl=fetch}={}){
 if(!clientId||!clientSecret||!refreshToken)throw Error('Gmail OAuth configuration incomplete');
 async function token(){
  const form=new URLSearchParams({client_id:clientId,client_secret:clientSecret,refresh_token:refreshToken,grant_type:'refresh_token'});
  const r=await fetchImpl('https://oauth2.googleapis.com/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:form,signal:AbortSignal.timeout(12000)});
  if(!r.ok)throw Error('Gmail OAuth unavailable');
  const j=await r.json();if(typeof j.access_token!=='string')throw Error('Gmail OAuth response invalid');
  return j.access_token;
 }
 return {async inspect({date}){
  if(!DATE.test(date))throw Error('Invalid travel date');
  const access=await token(),headers={Authorization:`Bearer ${access}`};
  const q='(westbahn OR "Comfort Class") newer_than:12m';
  const messages=[];let next=null,pages=0;
  do{
   const url=new URL(gmail+'/messages');url.searchParams.set('q',q);url.searchParams.set('maxResults','100');
   if(next)url.searchParams.set('pageToken',next);
   const r=await fetchImpl(url,{headers,signal:AbortSignal.timeout(15000)});
   if(!r.ok)throw Error('Gmail search unavailable');
   const data=await r.json();for(const m of data.messages||[]){
    if(typeof m.id!=='string')continue;
    const msgRes=await fetchImpl(gmail+'/messages/'+encodeURIComponent(m.id)+'?format=full',{headers,signal:AbortSignal.timeout(15000)});
    if(!msgRes.ok)throw Error('Gmail message unavailable');
    const full=await msgRes.json();
    const subject=(full.payload?.headers||[]).find(x=>x.name?.toLowerCase()==='subject')?.value||'';
    messages.push({subject,snippet:full.snippet||'',body:flatten(full.payload).join(' ').slice(0,12000)});
   }
   next=typeof data.nextPageToken==='string'?data.nextPageToken:null;
  }while(next&&++pages<9);
  if(next)throw Error('Gmail search not exhaustive');
  // All pages and full message fetches completed for the scoped Gmail query.
  // This does not prove the absence of tickets outside Gmail.
  return evaluateBookingEmail(messages,date,{searchComplete:true});
 }};
}
