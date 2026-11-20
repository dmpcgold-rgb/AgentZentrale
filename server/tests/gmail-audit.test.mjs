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
test('Gmail OAuth errors fail closed',async()=>{
 const checker=createGmailAudit({clientId:'c',clientSecret:'s',refreshToken:'r',
 fetchImpl:async()=>({ok:false})});
 await assert.rejects(checker.inspect({date}),/OAuth/);
});
