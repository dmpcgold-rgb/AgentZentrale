/** Native client talks only to the user's own HTTPS gateway. */
export function validateServerUrl(value) {
  const url = (value || '').trim().replace(/\/+$/, '');
  if (!/^https:\/\/[a-z0-9.-]+(?::\d{2,5})?(?:\/[a-z0-9._~-]+)*$/i.test(url)) {
    throw new Error('Bitte eine HTTPS-Adresse eingeben, z. B. https://agent.example.at');
  }
  if (/^https:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(:|\/|$)/i.test(url)) {
    throw new Error('Auf Android ist localhost dein Smartphone. Verwende einen erreichbaren HTTPS-Server.');
  }
  return url;
}
export async function gatewayRequest(config, path, { method = 'GET', body, timeoutMs = 50_000 } = {}) {
  if (!config?.url || !config?.token) throw new Error('Bitte zuerst den KI-Server in den Einstellungen verbinden.');
  const url = validateServerUrl(config.url) + path;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { method, signal: controller.signal, headers: { Authorization: `Bearer ${config.token}`, 'Content-Type': 'application/json', Accept: 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    let data;
    try { data = await response.json(); } catch { throw new Error('Server hat kein gültiges JSON gesendet.'); }
    if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : `Serverfehler (${response.status})`);
    return data;
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error('Zeitüberschreitung bei der Serververbindung.');
    throw error;
  } finally { clearTimeout(timer); }
}
export const qs = (params) => '?' + Object.entries(params).map(([k,v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v ?? '')).join('&');
