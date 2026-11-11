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
  confirmationVerified:false};
 const browser={status:()=>({enabled:true,liveBooking:false}),
   async run(...args){calls.push(args);return expected;}};
 const westbahn={run(){throw Error('must not book')}};
 const handler=createAgentHandler({
   env:{AGENTZENTRALE_ACCESS_TOKEN:token},browser,westbahn
 });
 const result=await request(handler);
 assert.equal(result.status,200);
 assert.deepEqual(result.body,expected);
 assert.deepEqual(calls,[['ticket-detail-check',date,seat]]);
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
