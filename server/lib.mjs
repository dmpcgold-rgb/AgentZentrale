import { timingSafeEqual, randomBytes } from 'node:crypto';

export class ApiError extends Error {
  constructor(code, message) { super(message); this.status = code; }
}
export function compareToken(actual, expected) {
  if (!actual || !expected || typeof actual !== 'string') return false;
  const a = Buffer.from(actual); const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}
export function requireName(value, description='Name') {
  if (typeof value !== 'string' || !/^[a-z\d][a-z\d._-]{0,99}$/i.test(value) || value === '.' || value === '..') {
    throw new ApiError(400, `Ungültiger ${description}.`);
  }
  return value;
}
export function requirePath(value) {
  if (typeof value !== 'string' || value.length > 300 || !value || value.startsWith('/') || value.includes('\\') || /[\x00-\x1F\x7F]/.test(value)) throw new ApiError(400, 'Ungültiger Dateipfad.');
  const parts = value.split('/');
  if (parts.some(p => !p || p === '.' || p === '..') || parts.some(p => !/^[a-z\d ._@()+\-]+$/i.test(p))) throw new ApiError(400, 'Ungültiger Dateipfad.');
  return value;
}
export function enforceWritableFile(path) {
  const filename = path.split('/').at(-1).toLowerCase();
  if (path.toLowerCase().startsWith('.github/workflows/') || /(^|\/)(\.env($|\.)|\.git\/|id_rsa|credentials\.|secrets\.|google-services\.json)/i.test(path) || /\.(png|jpg|jpeg|gif|webp|pdf|zip|apk|keystore|jks)$/i.test(filename)) {
    throw new ApiError(403, 'Diese Datei darf über den Agenten nicht verändert werden.');
  }
  return path;
}
export function requireText(value, label, max=1500) {
  if (typeof value !== 'string' || !value.trim() || value.length > max) throw new ApiError(400, `Ungültig: ${label} (max. ${max} Zeichen).`);
  return value.trim();
}
export function isAllowedOwner(owner, csv) {
  if (!csv) return true;
  const allowed = csv.split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
  return allowed.includes(owner.toLowerCase());
}
export function apiPath(segments) { return '/' + segments.map(x => encodeURIComponent(x)).join('/'); }
export function responseText(payload) {
  if (!payload || !Array.isArray(payload.output)) throw new ApiError(502, 'KI-Antwort enthält keinen Text.');
  const text = payload.output.flatMap(o => Array.isArray(o.content) ? o.content : [])
    .filter(c => c.type === 'output_text' && typeof c.text === 'string')
    .map(c => c.text).join('\n').trim();
  if (!text) throw new ApiError(502, 'KI hat keinen Text zurückgegeben.');
  return text;
}
export function verifyProposalObject(value, original) {
  if (!value || typeof value !== 'object') throw new ApiError(502, 'Ungültiger KI-Änderungsvorschlag.');
  const title = requireText(value.title, 'Titel', 120);
  const summary = requireText(value.summary, 'Zusammenfassung', 1000);
  if (typeof value.content !== 'string' || !value.content.trim() || value.content.length > 30000) throw new ApiError(502, 'Ungültiger Dateiinhalt in KI-Antwort.');
  const content = value.content;
  if (content === original) throw new ApiError(422, 'KI hat keinen veränderten Dateiinhalt vorgeschlagen.');
  return { title, summary, content };
}
export function generateBranch() { return `agentzentrale/${new Date().toISOString().replace(/[:.]/g, '-')}-${randomBytes(4).toString('hex')}`; }
