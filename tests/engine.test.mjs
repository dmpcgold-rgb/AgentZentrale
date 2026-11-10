import test from 'node:test';
import assert from 'node:assert/strict';
import { AGENTS, initialState, prepareCommand, previewApproval, updateState, isValidStoredState, migrateStoredState } from '../src/core/engine.js';
const base = { at: '2026-11-09T12:00:00Z', eventId: 'e1' };

test('agent registry exposes exact enabled and disabled modules', () => {
  assert.equal(AGENTS.length, 7);
  assert.equal(AGENTS.find(a => a.id === 'code').active, true);
  assert.equal(AGENTS.find(a => a.id === 'ai').active, true);
});
test('tasks and reminders stay local', () => {
  assert.deepEqual(prepareCommand('Aufgabe Einkaufsliste prüfen'), { kind: 'task', agent: 'tasks', title: 'Einkaufsliste prüfen', reminder: false });
  assert.equal(prepareCommand('Erinnere mich an Milch').reminder, false);
});
test('note routing', () => {
  assert.deepEqual(prepareCommand('Notiz Alternative Standplätze'), { kind: 'note', agent: 'notes', content: 'Alternative Standplätze' });
});
test('external operations require approval', () => {
  const research = prepareCommand('Recherchiere Genehmigungen');
  const mail = prepareCommand('Schreibe eine E-Mail Anfrage');
  const cal = prepareCommand('Termin Arzt am Montag');
  assert.equal(research.kind, 'approval');
  assert.equal(research.type, 'web-search');
  assert.equal(mail.type, 'mail-draft');
  assert.equal(cal.type, 'calendar-draft');
  assert.match(previewApproval(mail), /keine E-Mail automatisch versendet/i);
});
test('unsupported or malformed commands do not create actions', () => {
  assert.equal(prepareCommand('Lösche alle E-Mails').kind, 'unsupported');
  assert.equal(prepareCommand('   ').kind, 'invalid');
  assert.equal(prepareCommand('Aufgabe').kind, 'invalid');
  assert.equal(prepareCommand('x'.repeat(1001)).kind, 'invalid');
});
test('task persistence model and toggle', () => {
  let state = initialState();
  state = updateState(state, { type: 'ADD_TASK', id: 't1', title: 'Buchung prüfen', ...base });
  assert.equal(state.tasks.length, 1);
  assert.equal(state.tasks[0].done, false);
  state = updateState(state, { type: 'TOGGLE_TASK', id: 't1', ...base });
  assert.equal(state.tasks[0].done, true);
  assert.equal(isValidStoredState(JSON.parse(JSON.stringify(state))), true);
  state = updateState(state, { type: 'DELETE_TASK', id: 't1', ...base });
  assert.equal(state.tasks.length, 0);
});
test('approval cannot be executed twice', () => {
  let state = updateState(initialState(), { type: 'QUEUE_APPROVAL', id: 'p1', agent: 'mail', actionType: 'mail-draft', label: 'E-Mail', payload: 'Anfrage', ...base });
  assert.equal(state.approvals[0].status, 'pending');
  state = updateState(state, { type: 'FINISH_APPROVAL', id: 'p1', status: 'approved', ...base });
  assert.equal(state.approvals[0].status, 'approved');
  const events = state.events.length;
  state = updateState(state, { type: 'FINISH_APPROVAL', id: 'p1', status: 'approved', ...base });
  assert.equal(state.events.length, events);
});
test('notes created and reset restores empty state', () => {
  let state = updateState(initialState(), { type: 'ADD_NOTE', id: 'n1', content: 'Notiz', ...base });
  assert.equal(state.notes.length, 1);
  assert.deepEqual(updateState(state, { type: 'RESET', ...base }), initialState());
});


test('migrate from V1 without losing any tasks, notes or approvals', () => {
  const old = { schema: 1, tasks: [{ id:'t', title: 'Alte Aufgabe' }], notes: [{ id:'n', content:'Behalten' }], approvals: [{ id:'p', status:'pending' }], events: [{ id:'e' }] };
  const newData = migrateStoredState(old);
  assert.equal(newData.schema, 2);
  assert.equal(newData.tasks[0].title, 'Alte Aufgabe');
  assert.equal(newData.notes[0].content, 'Behalten');
  assert.equal(newData.approvals[0].status, 'pending');
  assert.deepEqual(newData.chat, []);
  assert.equal(isValidStoredState(newData), true);
});
test('chat messages persist and can be cleared independently', () => {
  let state = updateState(initialState(), { type:'ADD_TASK', id:'t', title:'Bleibt', ...base });
  state = updateState(state, { type:'CHAT_MESSAGE', id:'c', role:'user', content:'Hallo', ...base });
  state = updateState(state, { type:'CHAT_MESSAGE', id:'a', role:'assistant', content:'Guten Tag', ...base });
  assert.deepEqual(state.chat.map(c => c.role), ['user','assistant']);
  state = updateState(state, { type:'CLEAR_CHAT', ...base });
  assert.equal(state.chat.length, 0);
  assert.equal(state.tasks.length, 1);
});
