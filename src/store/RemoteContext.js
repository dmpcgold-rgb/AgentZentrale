import React, { createContext, useContext, useEffect, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { gatewayRequest, validateServerUrl } from '../api/client';

const KEY_CONFIG = 'agentzentrale.gateway.config.v1';
const Context = createContext(null);

export function RemoteProvider({ children }) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');
  useEffect(() => {
    let valid = true;
    SecureStore.getItemAsync(KEY_CONFIG)
      .then(raw => { if (valid) { const next = raw ? JSON.parse(raw) : null; setConfig(next?.url && next?.token ? next : null); setLoading(false); } })
      .catch(() => { if (valid) { setNotice('Verbindungseinstellungen konnten nicht gelesen werden.'); setLoading(false); } });
    return () => { valid = false; };
  }, []);
  async function saveSettings(url, token) {
    const safeUrl = validateServerUrl(url);
    if (typeof token !== 'string' || token.trim().length < 24) throw new Error('Der Zugriffsschlüssel muss mindestens 24 Zeichen haben.');
    const newConfig = { url: safeUrl, token: token.trim() };
    // Test connection before persisting. Failed setup never replaces existing configuration.
    const health = await gatewayRequest(newConfig, '/health');
    await SecureStore.setItemAsync(KEY_CONFIG, JSON.stringify(newConfig));
    setConfig(newConfig); setNotice('');
    return health;
  }
  async function disconnect() {
    await SecureStore.deleteItemAsync(KEY_CONFIG);
    setConfig(null); setNotice('');
  }
  async function request(path, opts) { return gatewayRequest(config, path, opts); }
  return <Context.Provider value={{ connected: Boolean(config), config, loading, notice, request, saveSettings, disconnect }}>{children}</Context.Provider>;
}
export function useRemote() {
  const value = useContext(Context);
  if (!value) throw new Error('useRemote must be used inside RemoteProvider');
  return value;
}
