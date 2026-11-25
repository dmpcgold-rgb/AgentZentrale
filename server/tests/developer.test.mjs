import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createAgentHandler} from '../index.mjs';

const token='test-token-not-a-real-secret-123456';
const sha='a'.repeat(40);
const env={AGENTZENTRALE_ACCESS_TOKEN:token,GITHUB_ALLOWED_OWNERS:'owner',GITHUB_TOKEN:'mock',ENABLE_GITHUB_WRITE:'true',OPENAI_API_KEY:'mock'};
async function fixture(fn, extra={}, fetchImpl=async()=>{throw Error('Unexpected upstream request');}){
  const server=createServer(createAgentHandler({env:{...env,...extra},fetchImpl,browser:{},westbahn:{}}));
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const url='http://127.0.0.1:'+server.address().port;
  const req=(path,body,authorized=true)=>fetch(url+path,{method:body===undefined?'GET':'POST',headers:{...(authorized?{Authorization:'Bearer '+token}:{}),'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  try{await fn(req);}finally{await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});}
}
const proposal={owner:'owner',repo:'demo',paths:['src/a.js'],instruction:'Improve'};
test('developer routes require authentication',()=>fixture(async req=>{
  assert.equal((await req('/developer/plan',proposal,false)).status,401);
}));
test('developer blocks protected and duplicate paths without upstream calls',()=>fixture(async req=>{
  for(const paths of [['.github/workflows/build.yml'],['src/.env'],['src/a.js','src/a.js'],['src/key.pem'],['package.json']]){
    assert.equal((await req('/developer/plan',{...proposal,paths})).status,403);
  }
}));
test('developer blocks foreign repository owners',()=>fixture(async req=>{
  assert.equal((await req('/developer/plan',{...proposal,owner:'foreign'})).status,403);
  assert.equal((await req('/developer/checks?owner=foreign&repo=demo&sha='+sha)).status,403);
}));
test('draft and workflow actions require explicit authorization',()=>fixture(async req=>{
  assert.equal((await req('/developer/create-pr',{id:'none'})).status,403);
  assert.equal((await req('/developer/create-pr',{id:'none',confirm:'FREIGEBEN'})).status,410);
  assert.equal((await req('/developer/dispatch',{confirm:'WORKFLOW-STARTEN'})).status,403);
}));
test('workflow dispatch rejects default branch and malformed commit',()=>fixture(async req=>{
  const b={owner:'owner',repo:'demo',workflowId:1,confirm:'WORKFLOW-STARTEN'};
  assert.equal((await req('/developer/dispatch',{...b,branch:'main',sha})).status,400);
  assert.equal((await req('/developer/dispatch',{...b,branch:'agentzentrale/test',sha:'bad'})).status,400);
},{ENABLE_DEVELOPER_BUILD:'true'}));
test('empty checks never imply test success',()=>fixture(async req=>{
  const r=await req('/developer/checks?owner=owner&repo=demo&sha='+sha);
  assert.equal(r.status,200);
  assert.equal((await r.json()).allReportedPassed,false);
},{},async()=>new Response(JSON.stringify({total_count:0,check_runs:[]}))));
test('successful reported checks are not inferred for truncated lists',()=>fixture(async req=>{
  const r=await req('/developer/checks?owner=owner&repo=demo&sha='+sha);
  assert.equal((await r.json()).allReportedPassed,false);
},{},async()=>new Response(JSON.stringify({total_count:2,check_runs:[{name:'test',status:'completed',conclusion:'success'}]}))));
