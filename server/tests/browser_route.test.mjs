import test from 'node:test';
import assert from 'node:assert/strict';
import {createAgentHandler} from '../index.mjs';

const token='PRIVATE-SINGLE-USER-TEST-TOKEN-123456789';
const date='2026-11-17',seat='191D';

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
