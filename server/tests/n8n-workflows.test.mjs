import test from 'node:test';
import assert from 'node:assert/strict';
import {readdirSync,readFileSync} from 'node:fs';
test('all n8n templates remain inactive and use scoped internal endpoints',()=>{
 const dir=new URL('../../n8n/workflows/',import.meta.url);
 const files=readdirSync(dir).filter(x=>x.endsWith('.json'));
 assert.ok(files.length>=6);
 for(const file of files){
  const w=JSON.parse(readFileSync(new URL(file,dir),'utf8'));
  assert.equal(w.active,false,file);
  assert.ok(w.nodes.length>=2,file);
  const names=new Set(w.nodes.map(n=>n.name));
  for(const [name,connection] of Object.entries(w.connections)){
   assert.ok(names.has(name),file);
   for(const outputs of connection.main)for(const edge of outputs)assert.ok(names.has(edge.node),file);
  }
  for(const node of w.nodes){
   assert.ok(['n8n-nodes-base.manualTrigger','n8n-nodes-base.scheduleTrigger','n8n-nodes-base.httpRequest'].includes(node.type),file);
   assert.equal(node.credentials,undefined,file);
   if(node.type==='n8n-nodes-base.httpRequest'){
    assert.ok(['http://agentzentrale:8787/automation/status','http://agentzentrale:8787/automation/tasks'].includes(node.parameters.url),file);
    assert.equal(node.parameters.genericAuthType,'httpHeaderAuth',file);
    assert.equal(node.parameters.authentication,'genericCredentialType',file);
   }
  }
 }
});
