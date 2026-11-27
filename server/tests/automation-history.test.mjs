import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createAutomationHistory } from '../automation-history.mjs';
test('history survives reload and retains only bounded metadata',()=>{
 const dir=mkdtempSync(join(tmpdir(),'agent-history-'));
 try{
 const file=join(dir,'history.json');
 const history=createAutomationHistory(file);
 for(let i=0;i<105;i++) history.record({id:'job_test_'+i,type:'system-status',status:'completed',at:new Date(i*1000).toISOString(),secret:'not saved'});
 const restored=createAutomationHistory(file);
 assert.equal(restored.persistent(),true);
 assert.equal(restored.list().length,100);
 assert.equal(restored.list()[0].id,'job_test_104');
 assert.equal(JSON.stringify(restored.list()).includes('secret'),false);
 writeFileSync(file,'broken');
 assert.equal(createAutomationHistory(file).persistent(),false);
 }finally{rmSync(dir,{recursive:true,force:true});}
});
