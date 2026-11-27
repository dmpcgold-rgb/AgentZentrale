import test from 'node:test';
import assert from 'node:assert/strict';
import { createAutomationRouter } from '../automation-router.mjs';
test('allowlisted tasks, duplicate protection and validation',()=>{
 let calls=0; let time=0;
 const router=createAutomationRouter({now:()=>time,status:()=>({count:++calls}),readiness:()=>({bookingAuthorized:false}),reviewStatus:()=>({running:false})});
 const body={id:'test_0001',type:'system-status'};
 assert.equal(router.dispatch(body).result.count,1);
 assert.equal(router.dispatch(body).result.count,1);
 assert.throws(()=>router.dispatch({...body,type:'westbahn-readiness'}),{status:409});
 assert.throws(()=>router.dispatch({id:'test_0002',type:'book'}),{status:400});
 assert.throws(()=>router.dispatch({...body,url:'http://localhost'}),{status:400});
 time=600000;
 assert.equal(router.dispatch(body).result.count,2);
});
