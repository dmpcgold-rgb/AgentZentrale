import test from 'node:test';
import assert from 'node:assert/strict';
import {createWeeklyGmailConfirmation,validateWeeklyEmailEvidence} from '../gmail-confirmation.mjs';
import {createWestbahn} from '../westbahn.mjs';
import {createWeeklyReview} from '../weekly-review.mjs';
import {planDates} from '../../src/core/westbahn.js';
const now=()=>new Date('2026-11-23T06:00:00Z');
const days=planDates(now()).slice(0,5);

test('one process check returns only sanitized positive Gmail evidence',async()=>{
 let calls=0;
 const check=createWeeklyGmailConfirmation({
  env:{WESTBAHN_GMAIL_CONFIRMATION_ENABLED:'1',WESTBAHN_PYTHON:'python3'},
  exec:async(cmd,args,options)=>{
   calls++;
   assert.deepEqual(args.slice(1),['--dates',days.join(','),'--train','1009']);
   assert.equal(options.timeout,45000);
   return {stdout:JSON.stringify({status:'email_week_checked',bookingAuthorized:false,
    confirmed:[{date:days[0],seat:'233A',source:'official_email',secret:'NOT_RETURNED'}],
    conflictingDates:[],ticketNumber:'NEVER_FORWARD'})};
  }
 });
 const result=await check(days);
 assert.equal(calls,1);
 assert.deepEqual(result.confirmed,[{date:days[0],seat:'233A',source:'official_email'}]);
 assert.equal(JSON.stringify(result).includes('NOT_RETURNED'),false);
 assert.equal(JSON.stringify(result).includes('NEVER_FORWARD'),false);
 assert.equal(result.bookingAuthorized,false);
});

test('missing Gmail access and malformed output never confirm or authorize',async()=>{
 const unset=createWeeklyGmailConfirmation({env:{},exec:async()=>{throw Error('should not run')}});
 assert.equal((await unset(days)).status,'email_not_configured');
 for(const value of [null,{},{
  status:'email_week_checked',bookingAuthorized:true,
  confirmed:[{date:days[0],seat:'233A',source:'official_email'}],conflictingDates:[]
 },{
  status:'email_week_checked',bookingAuthorized:false,
  confirmed:[{date:days[0],seat:'233A',source:'official_email'},
             {date:days[0],seat:'233A',source:'official_email'}],
  conflictingDates:[]
 },{
  status:'email_week_checked',bookingAuthorized:false,
  confirmed:[{date:days[0],seat:'233A',source:'official_email'}],
  conflictingDates:[days[0]]
 }]){
  const res=validateWeeklyEmailEvidence(value,days);
  assert.equal(res.confirmed.length,0);
  assert.equal(res.bookingAuthorized,false);
 }
});

test('weekly read-only audit marks verified ticket email and avoids duplicate',async()=>{
 const ledger=createWestbahn({now});
 const browser={run:async(_mode,_date,_seat,dates)=>({
  status:'inventory_batch_read',inventoryComplete:false,
  safeToBook:false,bookingAuthorized:false,accountPageReads:1,
  days:dates.map(date=>({date,status:'review_required',seats:[],
   dateVerified:false,detailVerified:false,potentialDuplicate:false,safeToBook:false}))
 })};
 const review=createWeeklyReview({now,westbahn:ledger,browser,
  gmailConfirm:async ()=>({status:'email_week_checked',bookingAuthorized:false,
    confirmed:[{date:days[0],seat:'191D',source:'official_email'}],
    conflictingDates:[]})});
 const result=await review.run();
 assert.deepEqual(result.emailConfirmedDates,[days[0]]);
 const row=ledger.status().rows.find(x=>x.date===days[0]);
 assert.equal(row.status,'confirmed');
 assert.equal(row.seat,'191D');
 assert.equal(row.confirmationSource,'official_email');
 assert.equal(result.safeToBook,false);
 assert.equal(result.bookingAuthorized,false);
});

test('conflicting email seat cannot overwrite protected booking',()=>{
 const ledger=createWestbahn({now});
 ledger.recordVerifiedEmail(days[0],'191D');
 assert.throws(()=>ledger.recordVerifiedEmail(days[0],'233A'),/Abweichender/);
 assert.equal(ledger.status().rows.find(x=>x.date===days[0]).seat,'191D');
});

test('email absence never marks date free or initiates booking',async()=>{
 const ledger=createWestbahn({now});
 const browser={run:async(_mode,_date,_seat,dates)=>({
  status:'inventory_batch_read',inventoryComplete:false,
  safeToBook:false,bookingAuthorized:false,accountPageReads:1,
  days:dates.map(date=>({date,status:'review_required',seats:[],
   dateVerified:false,detailVerified:false,potentialDuplicate:false,safeToBook:false}))
 })};
 const review=createWeeklyReview({now,westbahn:ledger,browser,
   gmailConfirm:async()=>({status:'email_week_checked',bookingAuthorized:false,
     confirmed:[],conflictingDates:[]})});
 const output=await review.run();
 assert.equal(output.emailConfirmedDates.length,0);
 assert.equal(output.safeToBook,false);
 assert.equal(ledger.status().rows.length,0);
});
