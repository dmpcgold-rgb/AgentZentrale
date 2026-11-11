import test from 'node:test';
import assert from 'node:assert/strict';
import {bookingReadiness} from '../booking-readiness.mjs';
import {createWestbahn} from '../westbahn.mjs';

const now=()=>new Date('2026-11-11T13:00:00Z');
test('readiness explains protected and unverified days without making bookings',()=>{
 const westbahn=createWestbahn({now});
 westbahn.recordVerifiedExisting('2026-11-17','191D');
 const view=bookingReadiness({westbahn,now:now()});
 assert.equal(view.status,'checkout_not_ready');
 assert.deepEqual(view.preferredSeats,['233A','233D']);
 assert.deepEqual(view.alternativeSeats,['191D','182A']);
 assert.equal(view.days[0].status,'protected_existing');
 assert.equal(view.days[0].seat,'191D');
 assert.equal(view.days[1].status,'inventory_unverified');
 assert.ok(view.days.every(x=>x.bookable===false));
 assert.equal(view.canPurchase,false);
 assert.equal(view.fullInventoryVerified,false);
 assert.equal(view.maxTotalCents,0);
});
test('partial account reads never prove a day is open for checkout',()=>{
 const westbahn=createWestbahn({now});
 const review={status:()=>({lastRun:{days:[
  {date:'2026-11-18',status:'possible_existing'},
  {date:'2026-11-19',status:'review_required'}
 ]}})};
 const status=bookingReadiness({westbahn,review,now:now()});
 assert.equal(status.days[1].status,'possible_existing');
 assert.equal(status.days[2].status,'inventory_unverified');
 assert.equal(status.days[1].bookable,false);
 assert.equal(status.canPurchase,false);
});
test('an interrupted checkout remains a manual review blocker',()=>{
 const westbahn={status:()=>({rows:[
  {date:'2026-11-17',status:'uncertain',seat:'233A'},
  {date:'2026-11-18',status:'user_reported',seat:'182A'}
 ]})};
 const status=bookingReadiness({westbahn,now:now()});
 assert.equal(status.days[0].status,'checkout_needs_review');
 assert.equal(status.days[1].status,'reported_existing');
 assert.ok(status.blockers.includes('real_provider_checkout_adapter'));
 assert.equal(status.automaticBookingEnabled,false);
});
