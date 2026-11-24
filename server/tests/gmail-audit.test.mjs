import test from 'node:test';
import assert from 'node:assert/strict';
import {evaluateBookingEmail,createGmailAudit} from '../gmail-audit.mjs';

const date='2026-11-23';
test('email matching date, route and reservation blocks the day',()=>{
 const result=evaluateBookingEmail([{subject:'WESTbahn Buchungsbestätigung',
 body:'23.11.2026 Wien Meidling - Wiener Neustadt Hbf 18:22 Comfort Class Sitzplatzreservierung'}],date);
 assert.equal(result.possibleExisting,true);
 assert.equal(result.bookingAuthorized,false);
 assert.equal(result.absenceProven,false);
});
test('no matching mail is not evidence that there is no booking',()=>{
 const r=evaluateBookingEmail([],date);
 assert.equal(r.possibleExisting,false);
 assert.equal(r.absenceProven,false);
 assert.equal(r.mailboxComplete,false);
});
test('different travel date is not treated as the requested date',()=>{
 const r=evaluateBookingEmail([{subject:'WESTbahn Reservierung',body:'24.11.2026 Wien Meidling - Wiener Neustadt'}],date);
 assert.equal(r.possibleExisting,false);
});
test('actual WESTbahn message with abbreviated stations and Nov date is recognized',()=>{
 const r=evaluateBookingEmail([{subject:'Ihr Westbahn-Ticket',body:'Abfahrt 18:22 Di 24 Nov Ankunft 18:49 W. Meidling Wr. Neustadt 2+ | Reservierung Comfort Class'}],'2026-11-24');
 assert.equal(r.possibleExisting,true);
 assert.equal(evaluateBookingEmail([{subject:'Ihr Westbahn-Ticket',body:'Abfahrt 18:22 Di 24 Nov W. Meidling Wr. Neustadt 2+ Reservierung Comfort Class'}],'2026-11-25').possibleExisting,false);
});
test('Gmail OAuth errors fail closed',async()=>{
 const checker=createGmailAudit({clientId:'c',clientSecret:'s',refreshToken:'r',
 fetchImpl:async()=>({ok:false})});
 await assert.rejects(checker.inspect({date}),/OAuth/);
});

test('a completed, scoped Gmail search is recorded without authorizing checkout',()=>{
 const r=evaluateBookingEmail([],date,{searchComplete:true});
 assert.equal(r.searchComplete,true);
 assert.equal(r.mailboxComplete,true);
 assert.equal(r.absenceProven,false);
 assert.equal(r.bookingAuthorized,false);
 assert.equal(r.status,'no_matching_email_observed');
});
test('a partial Gmail search cannot claim completeness',()=>{
 const r=evaluateBookingEmail([],date);
 assert.equal(r.searchComplete,false);
 assert.equal(r.mailboxComplete,false);
});
