import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {DEFAULT_RESERVATION_PLAN,HORIZONS,validateReservationPlan,
  reservationDates,createReservationPlanStore} from '../reservation-plan.mjs';

test('default plan covers Mon-Fri and defaults to two-week horizon',()=>{
 assert.deepEqual(DEFAULT_RESERVATION_PLAN.weekdays,[1,2,3,4,5]);
 assert.equal(DEFAULT_RESERVATION_PLAN.origin,'Wien Meidling');
 assert.equal(DEFAULT_RESERVATION_PLAN.destination,'Wiener Neustadt Hbf');
 assert.equal(DEFAULT_RESERVATION_PLAN.departure,'18:22');
 assert.equal(DEFAULT_RESERVATION_PLAN.horizon,'2w');
 assert.deepEqual(HORIZONS,['1w','2w','4w','2m','6m']);
 const dates=reservationDates(DEFAULT_RESERVATION_PLAN,new Date('2026-11-23T06:00:00Z'));
 assert.equal(dates[0],'2026-11-23');
 assert.equal(dates.length,10);
 assert.equal(dates.at(-1),'2026-12-04');
});

test('weekend tiles generate Saturdays and Sundays without weekdays',()=>{
 const settings=validateReservationPlan({...DEFAULT_RESERVATION_PLAN,weekdays:[7,6],horizon:'1w'});
 const dates=reservationDates(settings,new Date('2026-11-23T06:00:00Z'));
 assert.deepEqual(settings.weekdays,[6,7]);
 assert.deepEqual(dates,['2026-11-28','2026-11-29']);
});

test('one-week, four-week, two-month, six-month date horizons',()=>{
 const count={};
 for(const horizon of HORIZONS){
  const plan=validateReservationPlan({...DEFAULT_RESERVATION_PLAN,
    horizon,weekdays:[1,2,3,4,5,6,7]});
  const dates=reservationDates(plan,new Date('2026-11-23T06:00:00Z'));
  count[horizon]=dates.length;
  assert.ok(dates.every(x=>x>='2026-11-23'));
 }
 assert.equal(count['1w'],7);
 assert.equal(count['2w'],14);
 assert.equal(count['4w'],28);
 assert.ok(count['2m']>=59&&count['2m']<=63);
 assert.ok(count['6m']>=180&&count['6m']<=185);
});

test('weekday tile can include only Sunday and stores sorted numbers',()=>{
 const plan=validateReservationPlan({...DEFAULT_RESERVATION_PLAN,weekdays:[7,5,1]});
 assert.deepEqual(plan.weekdays,[1,5,7]);
});

test('invalid station, time windows, day numbers and oversized horizons rejected',()=>{
 for(const patch of [
  {origin:'   '},{origin:'Wien Meidling',destination:'Wien Meidling'},
  {departure:'24:00'},{departure:'18:2'}, {bookingWindowStart:'20:00',bookingWindowEnd:'08:00'},
  {bookingWindowStart:'12:00',bookingWindowEnd:'12:00'},
  {weekdays:[]},{weekdays:[1,1]},{weekdays:[0]},{weekdays:[8]},
  {weekdays:['1']},{horizon:'1y'},{maxPrice:99}
 ]){
  assert.throws(()=>validateReservationPlan({...DEFAULT_RESERVATION_PLAN,...patch}));
 }
});

test('store roundtrips and keeps old data after rejected edit',()=>{
 const dir=mkdtempSync(join(tmpdir(),'az-plan-'));
 try{
  const file=join(dir,'private-plan.json');
  const a=createReservationPlanStore({file});
  const newPlan=validateReservationPlan({...a.get(),origin:'Wien Westbahnhof',
     destination:'Salzburg Hbf',departure:'10:30',weekdays:[2,4,6],horizon:'6m',
     bookingWindowStart:'06:00',bookingWindowEnd:'08:00'});
  a.save(newPlan);
  assert.deepEqual(createReservationPlanStore({file}).get(),newPlan);
  assert.throws(()=>a.save({...newPlan,weekdays:[]}));
  assert.deepEqual(JSON.parse(readFileSync(file,'utf8')),newPlan);
 }finally{rmSync(dir,{recursive:true,force:true});}
});
