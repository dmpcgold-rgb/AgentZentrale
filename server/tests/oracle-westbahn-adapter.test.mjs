import test from 'node:test';
import assert from 'node:assert/strict';
import {createAdapter,summarizeReadOnlyEvidence} from '../oracle-westbahn-adapter.mjs';
import {createWestbahn,verifiedNoExistingTicket} from '../westbahn.mjs';

const date='2026-11-25';
const base={status:'inventory_evidence_inspected',date,pagesVerified:2,pagesFailed:0,
 inventoryComplete:false,potentialDuplicate:false,
 absenceEvidence:{status:'not_proven',reason:'provider_total_not_verified'}};

test('partial WESTbahn inventory never proves an absent ticket',()=>{
 const result=summarizeReadOnlyEvidence(base,date);
 assert.equal(result.status,'unknown');
 assert.equal(result.inventoryComplete,false);
 assert.equal(result.searchComplete,false);
 assert.equal(verifiedNoExistingTicket(result,date),false);
});
test('positive evidence from partial inventory is preserved as possible existing',()=>{
 const result=summarizeReadOnlyEvidence({...base,potentialDuplicate:true},date);
 assert.equal(result.possibleExisting,true);
 assert.equal(result.matchingTicketFound,true);
 assert.equal(verifiedNoExistingTicket(result,date),false);
});
test('invalid date, failed login, failed page and mismatched dates fail closed',async()=>{
 assert.throws(()=>summarizeReadOnlyEvidence(base,'2026-02-30'),/Reisedatum/);
 const checked=summarizeReadOnlyEvidence({...base,pagesFailed:1},date);
 assert.equal(checked.accountVerified,false);
 const adapter=createAdapter({execute:async()=>({stdout:JSON.stringify({...base,date:'2026-11-26'})})});
 const result=await adapter.existing({date});
 assert.equal(result.status,'unknown');
 assert.equal(result.accountVerified,false);
 assert.equal(result.inventoryComplete,false);
});
test('read-only adapter runs only safe worker command, never a checkout',async()=>{
 let observed;
 const adapter=createAdapter({execute:async (bin,args,opts)=>{
   observed={bin,args,opts};
   return {stdout:JSON.stringify(base)};
 }});
 const found=await adapter.existing({date});
 assert.deepEqual(observed.args.slice(1),['reservation-pages-check','--date',date]);
 assert.equal(observed.bin,'python3');
 assert.equal(found.searchComplete,false);
 assert.equal(adapter.capabilities.liveCheckout,false);
 for(const name of ['search','quote','book'])await assert.rejects(
   adapter[name]({date}),/nur lesend/);
});
test('existing orchestrator cannot book with this adapter',async()=>{
 let checks=0;
 const adapter=createAdapter({execute:async()=>{
   checks++;
   return {stdout:JSON.stringify(base)};
 }});
 const agent=createWestbahn({now:()=>new Date('2026-11-24T12:00:00Z'),
   adapter,emailAudit:{inspect:async()=>{throw Error('must not reach Gmail')}},liveCheckoutEnabled:true});
 await agent.run({dates:[date]});
 assert.equal(checks,1);
 assert.equal(agent.status().rows.find(x=>x.date===date).status,'blocked');
});
