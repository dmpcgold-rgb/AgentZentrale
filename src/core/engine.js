/*
 * AgentZentrale v1: deterministic, offline command routing.
 * This is not a generative AI model; no real mail is sent, no calendar event
 * is created, and no web search is made before explicit approval.
 */
export const AGENTS = Object.freeze([
  { id: 'tasks', name: 'Aufgaben-Agent', icon: 'checkbox-outline', description: 'Aufgaben anlegen und abhaken', active: true },
  { id: 'notes', name: 'Notizen-Agent', icon: 'document-text-outline', description: 'Notizen lokal speichern', active: true },
  { id: 'research', name: 'Recherche-Agent', icon: 'search-outline', description: 'Websuche nach Freigabe öffnen', active: true },
  { id: 'mail', name: 'Kommunikations-Agent', icon: 'mail-outline', description: 'E-Mail-Entwurf für Teilen vorbereiten', active: true },
  { id: 'calendar', name: 'Kalender-Agent', icon: 'calendar-outline', description: 'Terminnotiz für Teilen vorbereiten', active: true },
  { id: 'code', name: 'GitHub-Agent', icon: 'code-slash-outline', description: 'Dateien lesen, KI-Änderungsvorschläge und PRs mit Freigabe', active: true },
  { id: 'ai', name: 'KI-Assistent', icon: 'chatbubbles-outline', description: 'Online-Chat über einen eigenen geschützten Server', active: true }
]);

const strip = (s) => s.trim().replace(/^[\s:.,–-]+|[\s]+$/g, '');
const valueAfter = (s, pattern) => strip(s.replace(pattern, ''));

export function prepareCommand(value) {
  const text = typeof value === 'string' ? value.trim() : '';
  if (!text) return { kind: 'invalid', message: 'Bitte einen Befehl eingeben.' };
  if (text.length > 1000) return { kind: 'invalid', message: 'Der Befehl darf höchstens 1000 Zeichen haben.' };

  if (/^(notiz|notiere|merke dir|schreib(?:e)? auf)\b/i.test(text)) {
    const content = valueAfter(text, /^(notiz|notiere|merke dir|schreib(?:e)? auf)\b/i);
    return content ? { kind: 'note', agent: 'notes', content } : { kind: 'invalid', message: 'Was soll ich notieren?' };
  }
  if (/^(aufgabe|to[ -]?do|erinnere mich(?: daran)?|merke als aufgabe)\b/i.test(text)) {
    const title = valueAfter(text, /^(aufgabe|to[ -]?do|erinnere mich(?: daran)?|merke als aufgabe)\b/i);
    return title ? { kind: 'task', agent: 'tasks', title, reminder: false } : { kind: 'invalid', message: 'Welche Aufgabe soll ich anlegen?' };
  }
  if (/^(recherchiere|recherchier|suche im internet(?: nach)?|websuche|google(?: nach)?)\b/i.test(text)) {
    const query = valueAfter(text, /^(recherchiere|recherchier|suche im internet(?: nach)?|websuche|google(?: nach)?)\b/i);
    return query ? { kind: 'approval', agent: 'research', type: 'web-search', label: `Websuche: ${query}`, payload: query } : { kind: 'invalid', message: 'Wonach soll ich suchen?' };
  }
  if (/^(e-?mail|mail|schreibe (?:eine? )?(?:e-?mail|nachricht)|entwirf (?:eine? )?(?:e-?mail|nachricht))\b/i.test(text)) {
    const subject = valueAfter(text, /^(e-?mail|mail|schreibe (?:eine? )?(?:e-?mail|nachricht)|entwirf (?:eine? )?(?:e-?mail|nachricht))\b/i);
    return subject ? { kind: 'approval', agent: 'mail', type: 'mail-draft', label: 'E-Mail-Entwurf teilen', payload: subject } : { kind: 'invalid', message: 'Welches Thema soll die E-Mail haben?' };
  }
  if (/^(termin|kalender|plane (?:einen? )?termin|erstelle (?:einen? )?termin)\b/i.test(text)) {
    const details = valueAfter(text, /^(termin|kalender|plane (?:einen? )?termin|erstelle (?:einen? )?termin)\b/i);
    return details ? { kind: 'approval', agent: 'calendar', type: 'calendar-draft', label: 'Terminnotiz teilen', payload: details } : { kind: 'invalid', message: 'Welche Termindetails soll ich notieren?' };
  }
  return { kind: 'unsupported', message: 'Noch nicht unterstützt. Versuche „Aufgabe …“, „Notiz …“, „Recherchiere …“, „E-Mail …“ oder „Termin …“.' };
}

export function initialState() {
  return { schema: 2, tasks: [], notes: [], approvals: [], events: [], chat: [] };
}

export function isValidStoredState(state) {
  return Boolean(state && state.schema === 2 && ['tasks', 'notes', 'approvals', 'events', 'chat'].every(k => Array.isArray(state[k])));
}

export function migrateStoredState(state) {
  if (isValidStoredState(state)) return state;
  if (state && state.schema === 1 && ['tasks', 'notes', 'approvals', 'events'].every(k => Array.isArray(state[k]))) {
    return { ...state, schema: 2, chat: [] };
  }
  throw new Error('Unbekanntes Speicherformat');
}

export function updateState(state, event) {
  const now = event.at || new Date().toISOString();
  switch (event.type) {
    case 'ADD_TASK': {
      const task = { id: event.id, title: event.title, done: false, createdAt: now };
      return { ...state, tasks: [task, ...state.tasks], events: [{ id: event.eventId, at: now, text: 'Aufgabe angelegt: ' + event.title }, ...state.events].slice(0, 150) };
    }
    case 'ADD_NOTE': {
      const note = { id: event.id, content: event.content, createdAt: now };
      return { ...state, notes: [note, ...state.notes], events: [{ id: event.eventId, at: now, text: 'Notiz gespeichert' }, ...state.events].slice(0, 150) };
    }
    case 'QUEUE_APPROVAL': {
      const approval = { id: event.id, agent: event.agent, type: event.actionType, label: event.label, payload: event.payload, createdAt: now, status: 'pending' };
      return { ...state, approvals: [approval, ...state.approvals], events: [{ id: event.eventId, at: now, text: 'Freigabe angefragt: ' + event.label }, ...state.events].slice(0, 150) };
    }
    case 'FINISH_APPROVAL': {
      const approval = state.approvals.find(a => a.id === event.id);
      if (!approval || approval.status !== 'pending') return state;
      return { ...state, approvals: state.approvals.map(a => a.id === event.id ? { ...a, status: event.status } : a), events: [{ id: event.eventId, at: now, text: (event.status === 'approved' ? 'Freigegeben: ' : event.status === 'failed' ? 'Fehlgeschlagen: ' : 'Abgelehnt: ') + approval.label }, ...state.events].slice(0, 150) };
    }
    case 'TOGGLE_TASK': {
      const task = state.tasks.find(t => t.id === event.id);
      if (!task) return state;
      return { ...state, tasks: state.tasks.map(t => t.id === event.id ? { ...t, done: !t.done } : t), events: [{ id: event.eventId, at: now, text: (!task.done ? 'Erledigt: ' : 'Wieder geöffnet: ') + task.title }, ...state.events].slice(0, 150) };
    }
    case 'DELETE_TASK':
      return { ...state, tasks: state.tasks.filter(t => t.id !== event.id), events: [{ id: event.eventId, at: now, text: 'Aufgabe nach Bestätigung gelöscht' }, ...state.events].slice(0, 150) };
    case 'DELETE_NOTE':
      return { ...state, notes: state.notes.filter(n => n.id !== event.id), events: [{ id: event.eventId, at: now, text: 'Notiz nach Bestätigung gelöscht' }, ...state.events].slice(0, 150) };
    case 'CHAT_MESSAGE': {
      const entry = { id: event.id, role: event.role, content: event.content, at: now };
      if (!['user', 'assistant'].includes(entry.role) || typeof entry.content !== 'string') return state;
      return { ...state, chat: [...state.chat, entry].slice(-40) };
    }
    case 'CLEAR_CHAT':
      return { ...state, chat: [], events: [{ id: event.eventId, at: now, text: 'KI-Chatverlauf gelöscht' }, ...state.events].slice(0, 150) };
    case 'LOG_ACTIVITY':
      return { ...state, events: [{ id: event.eventId, at: now, text: String(event.text || '').slice(0, 250) }, ...state.events].slice(0, 150) };
    case 'RESET':
      return initialState();
    default:
      return state;
  }
}

export function previewApproval(approval) {
  if (approval.type === 'web-search') return `Die folgende Websuche wird im Browser geöffnet:\n\n${approval.payload}\n\nEs findet keine automatische Analyse der Suchergebnisse statt.`;
  if (approval.type === 'mail-draft') return `Betreff: ${approval.payload}\n\nGuten Tag,\n\nich möchte mich bezüglich „${approval.payload}“ an Sie wenden.\n\n[Hier konkrete Angaben ergänzen und den Text überprüfen.]\n\nMit freundlichen Grüßen\n\nDies ist nur ein Entwurf. Es wird keine E-Mail automatisch versendet.`;
  if (approval.type === 'calendar-draft') return `Terminnotiz: ${approval.payload}\n\nDatum, Uhrzeit und Teilnehmer bitte prüfen und im Kalender selbst eintragen. Es wird kein Termin automatisch erstellt.`;
  return 'Unbekannte Aktion – keine Ausführung möglich.';
}
