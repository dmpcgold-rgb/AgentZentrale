import test from 'node:test';
import assert from 'node:assert/strict';
import {validateControl,enqueueControl,controlResult} from '../oracle-control.mjs';
import {normalizeHostStatus} from '../oracle-status.mjs';
import {mkdtemp,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
test('only explicit fixed operations allowed',()=>{
 assert.throws(()=>validateControl({action:'start',confirm:'WESTBAHN-STEUERUNG'}));
 assert.throws(()=>validateControl({action:'pause'}));
 assert.throws(()=>validateControl({action:'schedule',time:'07:00; reboot',confirm:'WESTBAHN-STEUERUNG'}));
 assert.deepEqual(validateControl({action:'schedule',time:'07:00',confirm:'WESTBAHN-STEUERUNG'}),{action:'schedule',time:'07:00'});
});
test('queue acceptance differs from execution',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'oracle-control-'));
 try{
  const r=await enqueueControl(dir,{action:'pause',confirm:'WESTBAHN-STEUERUNG'});
  await rm(join(dir,r.id+'.json'));
  assert.equal((await controlResult(dir,r.id)).status,'pending');
  await writeFile(join(dir,r.id+'.json'),JSON.stringify({id:r.id,ok:true}));
  assert.equal((await controlResult(dir,r.id)).status,'completed');
  await assert.rejects(controlResult(dir,'../../secret'));
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('stale host status is rejected',()=>{
 const now=Date.now(),v={timestamp:new Date(now-180000).toISOString(),timer:{ActiveState:'active'},service:{ActiveState:'inactive'}};
 assert.throws(()=>normalizeHostStatus(v,now));
});

test('weekly horizon accepts only one to three weeks and preserves month compatibility',()=>{
 const base={action:'horizon',confirm:'WESTBAHN-STEUERUNG'};
 for(const weeks of [1,2,3])assert.deepEqual(validateControl({...base,weeks}),{action:'horizon',weeks});
 for(const months of [1,2,3,4,5,6])assert.deepEqual(validateControl({...base,months}),{action:'horizon',months});
 for(const weeks of [0,4,-1,1.5,'2',true])assert.throws(()=>validateControl({...base,weeks}));
 assert.throws(()=>validateControl({...base,weeks:2,months:1}));
 const now=Date.now(),v={timestamp:new Date(now).toISOString(),timer:{ActiveState:'active'},service:{ActiveState:'inactive'},monthsAhead:6,weeksAhead:2};
 assert.equal(normalizeHostStatus(v,now).weeksAhead,2);
 assert.equal(normalizeHostStatus({...v,weeksAhead:4},now).weeksAhead,null);
});
