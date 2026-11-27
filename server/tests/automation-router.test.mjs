import test from 'node:test';
import assert from 'node:assert/strict';
import { createAutomationRouter } from '../automation-router.mjs';
test('allowlisted tasks, duplicate protection and validation',async()=>{
 let calls=0; let time=0;
 const router=createAutomationRouter({now:()=>time,status:()=>({count:++calls}),readiness:()=>({bookingAuthorized:false}),reviewStatus:()=>({running:false}),buildStatus:async()=>({runs:[]}),qualityStatus:()=>({runtimeTestsVerified:false})});
 const body={id:'test_0001',type:'system-status'};
 assert.equal((await router.dispatch(body)).result.count,1);
 assert.equal((await router.dispatch(body)).result.count,1);
 await assert.rejects(router.dispatch({...body,type:'westbahn-readiness'}),{status:409});
 await assert.rejects(router.dispatch({id:'test_0002',type:'book'}),{status:400});
 await assert.rejects(router.dispatch({...body,url:'http://localhost'}),{status:400});
 assert.deepEqual((await router.dispatch({id:'test_0003',type:'github-build-status'})).result,{runs:[]});
 assert.equal((await router.dispatch({id:'test_0004',type:'quality-status'})).result.runtimeTestsVerified,false);
 time=600000;
 assert.equal((await router.dispatch(body)).result.count,2);
});
test('concurrent identical requests share one execution',async()=>{
 let count=0;
 const router=createAutomationRouter({buildStatus:async()=>({count:++count})});
 const body={id:'build_0001',type:'github-build-status'};
 const results=await Promise.all([router.dispatch(body),router.dispatch(body)]);
 assert.equal(count,1);
 assert.deepEqual(results[0],results[1]);
});

test('history contains only metadata and records failures once',async()=>{
 const router=createAutomationRouter({status:()=>({secret:'not logged'}),gmailStatus:async()=>{throw Error('private error');}});
 await router.dispatch({id:'history_01',type:'system-status'});
 const job={id:'history_02',type:'gmail-connection-status'};
 await assert.rejects(router.dispatch(job));await assert.rejects(router.dispatch(job));
 assert.equal(router.history().length,2);
 assert.equal(router.history()[0].status,'failed');
 assert.equal(router.history()[1].status,'completed');
 assert.equal(JSON.stringify(router.history()).includes('secret'),false);
});

test('only transient GitHub reads retry once',async()=>{
 let calls=0;
 const router=createAutomationRouter({sleep:async()=>{},buildStatus:async()=>{if(++calls===1)throw Object.assign(Error('temporary'),{status:502});return {ok:true};},gmailStatus:async()=>{throw Object.assign(Error('temporary'),{status:502});}});
 assert.equal((await router.dispatch({id:'retry_001',type:'github-build-status'})).result.ok,true);
 assert.equal(calls,2);
 await assert.rejects(router.dispatch({id:'retry_002',type:'gmail-connection-status'}));
});
