import React, { createContext, useContext, useEffect, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { initialState, migrateStoredState, prepareCommand, updateState } from '../core/engine';
import { T } from '../theme';

const STORAGE_KEY = 'agentzentrale:state:v1';
const Context = createContext(null);
const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

export function DataProvider({ children }) {
  const [data, setData] = useState(null);
  const [storageError, setStorageError] = useState('');
  const [canSave, setCanSave] = useState(true);

  useEffect(() => {
    let open = true;
    async function load() {
      try {
        const raw = await AsyncStorage.getItem(STORAGE_KEY);
        const parsed = raw ? migrateStoredState(JSON.parse(raw)) : initialState();
        if (open) setData(parsed);
      } catch {
        if (open) {
          setStorageError('Lokale Daten konnten nicht gelesen werden. Zur Sicherheit wird der Speicher nicht überschrieben.');
          setCanSave(false);
          setData(initialState());
        }
      }
    }
    load();
    return () => { open = false; };
  }, []);

  useEffect(() => {
    if (!data || !canSave) return;
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(data)).catch(() => setStorageError('Speichern fehlgeschlagen – bitte freien Gerätespeicher prüfen.'));
  }, [data, canSave]);

  function apply(event) {
    setData(prev => prev ? updateState(prev, { ...event, at: new Date().toISOString(), eventId: uid() }) : prev);
  }

  function submitCommand(input) {
    const plan = prepareCommand(input);
    if (plan.kind === 'task') {
      apply({ type: 'ADD_TASK', id: uid(), title: plan.title });
      return { ok: true, message: 'Aufgabe lokal gespeichert. Es wurde keine Push-Erinnerung eingerichtet.' };
    }
    if (plan.kind === 'note') {
      apply({ type: 'ADD_NOTE', id: uid(), content: plan.content });
      return { ok: true, message: 'Notiz auf diesem Gerät gespeichert.' };
    }
    if (plan.kind === 'approval') {
      apply({ type: 'QUEUE_APPROVAL', id: uid(), agent: plan.agent, actionType: plan.type, label: plan.label, payload: plan.payload });
      return { ok: true, message: 'Aktion vorbereitet. Vor einer externen Aktion ist deine Freigabe erforderlich.' };
    }
    return { ok: false, message: plan.message };
  }

  async function resetStorage() {
    try {
      await AsyncStorage.removeItem(STORAGE_KEY);
      setCanSave(true);
      setStorageError('');
      setData(initialState());
    } catch {
      setStorageError('Zurücksetzen fehlgeschlagen.');
    }
  }

  if (!data) {
    return <View style={{ flex: 1, backgroundColor: T.bg, alignItems: 'center', justifyContent: 'center', gap: 16 }}>
      <ActivityIndicator size="large" color={T.accent} />
      <Text style={{ color: T.muted }}>Lokale Daten werden geladen …</Text>
    </View>;
  }

  return <Context.Provider value={{ data, apply, submitCommand, resetStorage, storageError, canSave }}>{children}</Context.Provider>;
}

export function useData() {
  const value = useContext(Context);
  if (!value) throw new Error('useData requires DataProvider');
  return value;
}
