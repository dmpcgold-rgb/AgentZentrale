import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const workflow = readFileSync(new URL('../.github/workflows/deploy-oracle.yml', import.meta.url), 'utf8');

test('automatic deployment requires successful main-branch test run from same repository', () => {
  assert.match(workflow, /github\.event\.workflow_run\.conclusion == 'success'/);
  assert.match(workflow, /github\.event\.workflow_run\.head_branch == 'main'/);
  assert.match(workflow, /github\.event\.workflow_run\.head_repository\.full_name == github\.repository/);
  assert.match(workflow, /needs: verify/);
});

test('deployment pins successful test commit and rejects stale main', () => {
  assert.match(workflow, /workflow_run\.head_sha/);
  assert.match(workflow, /git rev-parse FETCH_HEAD/);
  assert.match(workflow, /\[ "\$actual" != "\$expected" \]/);
  assert.match(workflow, /merge --ff-only "\$expected"/);
});

test('rollback checks restored container health and fails deployment', () => {
  assert.match(workflow, /checkout -B main "\$previous"/);
  assert.match(workflow, /restored_healthy=0/);
  assert.match(workflow, /restored_state" = healthy/);
  assert.match(workflow, /Previous version restored and healthy/);
  assert.match(workflow, /Rollback failed; manual recovery required/);
  assert.match(workflow, /exit 1\s+fi\s+echo "AgentZentrale deployment healthy"/);
});

test('deployment uses protected environment and serialized runs', () => {
  assert.match(workflow, /environment: oracle-production/);
  assert.match(workflow, /cancel-in-progress: false/);
  assert.match(workflow, /StrictHostKeyChecking=yes/);
});

test('production deployment is disabled unless explicitly opted in', () => {
  assert.match(workflow, /vars\.ORACLE_AUTO_DEPLOY_ENABLED == 'true'/);
  assert.match(workflow, /environment: oracle-production/);
});
