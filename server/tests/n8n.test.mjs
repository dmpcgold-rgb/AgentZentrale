import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createAgentHandler } from '../index.mjs';
test('n8n token is read-only and cannot access booking or chat', async () => {
  const token='w'.repeat(40), admin='a'.repeat(40);
  const server=createServer(createAgentHandler({env:{AGENTZENTRALE_ACCESS_TOKEN:admin,N8N_READ_TOKEN:token},westbahn:{status:()=>({providerConnected:false,running:false})},browser:{}}));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try {
    const url='http://127.0.0.1:'+server.address().port;
    const call=(path,method='GET',key=token)=>fetch(url+path,{method,headers:{Authorization:'Bearer '+key}});
    const status=await call('/automation/status');
    assert.equal(status.status,200);
    assert.equal((await status.json()).bookingAuthorized,false);
    for(const path of ['/westbahn/run','/chat','/github/create-pr','/automation/status']) assert.equal((await call(path,'POST')).status,403);
    assert.equal((await call('/health')).status,403);
    assert.equal((await call('/automation/status','GET','wrong')).status,401);
    assert.equal((await call('/health','GET',admin)).status,200);
  } finally { await new Promise(resolve=>server.close(resolve)); }
});
