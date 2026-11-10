import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createAgentHandler } from '../index.mjs';

const secret = '0123456789abcdef0123456789abcdef';
const env = { AGENTZENTRALE_ACCESS_TOKEN: secret, OPENAI_API_KEY: 'mock-openai', OPENAI_MODEL: 'gpt-4.1-mini', GITHUB_TOKEN: 'mock-github', ENABLE_GITHUB_WRITE: 'true', GITHUB_ALLOWED_OWNERS: 'dmpcgold-rgb' };
const repoInfo = { default_branch: 'main' };
const file = { type:'file', encoding:'base64', size:4, content:Buffer.from('alt\n').toString('base64'), sha:'before_sha', html_url:'https://github.com/dmpcgold-rgb/Test/blob/main/App.js' };
const calls = [];
async function mockFetch(url, options) {
  calls.push({ url:String(url), method:options.method || 'GET', body:options.body && JSON.parse(options.body) });
  const u = new URL(url); let result;
  if (u.host === 'api.openai.com') {
    const input = options.body ? JSON.parse(options.body) : {};
    assert.equal(input.store, false);
    assert.equal(input.tools, undefined);
    const code = input.text ? JSON.stringify({ title:'Datei verbessern', summary:'Testweise geändert', content:'neu\n' }) : 'Hallo aus KI!';
    result = { output: [{ content: [{ type:'output_text', text:code }] }] };
  } else if (u.pathname.endsWith('/contents/App.js') && options.method === 'PUT') result = { content: { sha:'after_sha' } };
  else if (u.pathname.endsWith('/contents/App.js')) result = file;
  else if (u.pathname.endsWith('/git/ref/heads/main')) result = { object: { sha:'base_commit_sha' } };
  else if (u.pathname.endsWith('/git/refs') && options.method === 'POST') result = { ref:'refs/heads/agentzentrale/test' };
  else if (u.pathname.endsWith('/pulls') && options.method === 'POST') result = { number:42, html_url:'https://github.com/dmpcgold-rgb/Test/pull/42' };
  else if (u.pathname.endsWith('/repos/dmpcgold-rgb/Test')) result = repoInfo;
  else if (u.pathname.endsWith('/users/dmpcgold-rgb/repos')) result = [{ name:'Test', private:false, description:'Example', default_branch:'main' }];
  else if (u.pathname.endsWith('/contents')) result = [{ name:'App.js', path:'App.js', size:4, type:'file' }];
  else throw Error(`Unexpected mock URL ${url}`);
  return new Response(JSON.stringify(result), { status:200, headers:{ 'Content-Type':'application/json' } });
}
async function setup(t, e=env) {
  calls.length = 0;
  const server = createServer(createAgentHandler({ env:e, fetchImpl:mockFetch }));
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  async function req(path, opts={}) {
    const r = await fetch(base+path, { method: opts.method || 'GET', headers: { Authorization:`Bearer ${opts.token || secret}`, 'Content-Type':'application/json' }, body:opts.body === undefined ? undefined : JSON.stringify(opts.body) });
    return { status:r.status, body:await r.json() };
  }
  return req;
}

test('health rejects unauthorized tokens, shows enabled services', async t => {
  const req = await setup(t);
  const no = await req('/health', {token:'wrong'});
  assert.equal(no.status, 401);
  const ok = await req('/health');
  assert.equal(ok.status, 200);
  assert.equal(ok.body.githubWriteEnabled, true);
});
test('chat uses Responses API without tools', async t => {
  const req = await setup(t);
  const chat = await req('/chat', { method:'POST', body:{message:'Hallo',history:[]} });
  assert.equal(chat.status, 200);
  assert.equal(chat.body.answer, 'Hallo aus KI!');
  assert.equal(calls.filter(c=>c.url.includes('/v1/responses')).length, 1);
});
test('GitHub browsing is read-only and respects owner allowlist', async t => {
  const req = await setup(t);
  const repos = await req('/github/repos?owner=dmpcgold-rgb');
  assert.equal(repos.status, 200);
  assert.equal(repos.body.repos[0].name, 'Test');
  const content = await req('/github/file?owner=dmpcgold-rgb&repo=Test&path=App.js');
  assert.equal(content.body.content, 'alt\n');
  const badOwner = await req('/github/file?owner=outsider&repo=Test&path=App.js');
  assert.equal(badOwner.status, 403);
  assert.equal(calls.filter(c => ['PUT','PATCH','DELETE','POST'].includes(c.method)).length, 0);
});
test('proposal returns preview but makes no write until explicit approval', async t => {
  const req = await setup(t);
  const preview = await req('/github/proposals', { method:'POST', body:{owner:'dmpcgold-rgb',repo:'Test',path:'App.js',instruction:'Schreibe neu'} });
  assert.equal(preview.status, 200);
  assert.equal(preview.body.proposed, 'neu\n');
  assert.ok(preview.body.id);
  assert.equal(calls.filter(c => c.url.startsWith('https://api.github.com') && ['PUT','POST'].includes(c.method)).length, 0);
  const denied = await req('/github/create-pr', {method:'POST',body:{id:preview.body.id,confirm:'NEIN'}});
  assert.equal(denied.status, 403);
  const created = await req('/github/create-pr', {method:'POST',body:{id:preview.body.id,confirm:'FREIGEBEN'}});
  assert.equal(created.status, 200);
  assert.equal(created.body.number, 42);
  assert.equal(calls.filter(c => c.url.includes('/pulls') && c.method==='POST').length, 1);
  assert.equal(calls.filter(c => c.method === 'PUT')[0].body.branch.startsWith('agentzentrale/'), true);
  const again = await req('/github/create-pr', {method:'POST',body:{id:preview.body.id,confirm:'FREIGEBEN'}});
  assert.equal(again.status, 410);
});
test('GitHub write cannot occur without opt-in switch', async t => {
  const req = await setup(t, { ...env, ENABLE_GITHUB_WRITE:'false' });
  const blocked = await req('/github/create-pr', {method:'POST',body:{id:'missing',confirm:'FREIGEBEN'}});
  assert.equal(blocked.status, 403);
});


test('daily AI usage ceiling is enforced server-side', async t => {
  const req = await setup(t, { ...env, AI_DAILY_LIMIT:'1' });
  const first = await req('/chat', { method:'POST', body:{message:'Hallo'} });
  assert.equal(first.status, 200);
  const second = await req('/chat', { method:'POST', body:{message:'Noch eine Frage'} });
  assert.equal(second.status, 429);
});
test('GitHub proposal rejects sensitive target files before AI call', async t => {
  const req = await setup(t);
  const attempted = await req('/github/proposals', { method:'POST', body:{owner:'dmpcgold-rgb',repo:'Test',path:'.env',instruction:'Schreibe um'} });
  assert.equal(attempted.status, 403);
  assert.equal(calls.filter(c=>c.url.includes('/v1/responses')).length, 0);
});
