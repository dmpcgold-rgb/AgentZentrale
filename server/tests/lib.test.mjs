import test from 'node:test';
import assert from 'node:assert/strict';
import { compareToken, requireName, requirePath, enforceWritableFile, requireText, responseText, verifyProposalObject, isAllowedOwner } from '../lib.mjs';
import { validateServerUrl, qs } from '../../src/api/client.js';

test('constant-time token matching requires exact token', () => {
  assert.equal(compareToken('abc123', 'abc123'), true);
  assert.equal(compareToken('abc123', 'abc124'), false);
  assert.equal(compareToken('abc', 'abc123'), false);
  assert.equal(compareToken('', 'abc123'), false);
});
test('repository and path cannot escape API scope', () => {
  assert.equal(requireName('Gym-Coach'), 'Gym-Coach');
  assert.equal(requirePath('src/screens/HubScreen.js'), 'src/screens/HubScreen.js');
  for (const path of ['../private', '/etc/passwd', 'foo/../secret', 'foo//bar', 'foo\\bar', 'foo?bar', 'x\ny']) assert.throws(() => requirePath(path));
  assert.throws(() => requireName('x/y'));
});
test('sensitive files are never write candidates', () => {
  for (const path of ['.github/workflows/main.yml', '.env', 'server/.env.production', 'secrets.json', 'google-services.json', 'foo.png', '.git/config']) {
    assert.throws(() => enforceWritableFile(path));
  }
  assert.equal(enforceWritableFile('src/App.js'), 'src/App.js');
});
test('proposal parsing and text enforcement', () => {
  assert.equal(responseText({ output: [{ content: [{ type:'output_text', text:'Hallo' }] }] }), 'Hallo');
  assert.deepEqual(verifyProposalObject({ title: 'Änderung', summary:'Kleine Korrektur', content:'neu' }, 'alt'), { title:'Änderung', summary:'Kleine Korrektur', content:'neu' });
  assert.throws(() => verifyProposalObject({ title:'x', summary:'y', content:'alt' }, 'alt'));
  assert.throws(() => requireText('', 'Text'));
});
test('allowlist denies non-authorized GitHub owners', () => {
  assert.equal(isAllowedOwner('dmpcgold-rgb', 'dmpcgold-rgb,other'), true);
  assert.equal(isAllowedOwner('unknown', 'dmpcgold-rgb,other'), false);
});
test('Android only accepts usable HTTPS gateways', () => {
  assert.equal(validateServerUrl('https://agent.example.at/'), 'https://agent.example.at');
  for (const url of ['http://example.com', 'https://localhost:8787', 'https://user:pass@server.com', '']) assert.throws(() => validateServerUrl(url));
  assert.equal(qs({owner:'test',repo:'my repo'}), '?owner=test&repo=my%20repo');
});
