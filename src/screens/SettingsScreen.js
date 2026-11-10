import React, { useState } from 'react';
import { Alert, ActivityIndicator, ScrollView, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useData } from '../store/DataContext';
import { useRemote } from '../store/RemoteContext';
import { T } from '../theme';
import { ActionButton, Body, Card, Heading, Muted, Section, styles } from '../components/Kit';

export default function SettingsScreen() {
  const { data, storageError, resetStorage } = useData();
  const { connected, config, loading, notice, request, saveSettings, disconnect } = useRemote();
  const [url, setUrl] = useState('');
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [health, setHealth] = useState(null);

  function confirmReset() {
    Alert.alert('Alle lokalen Daten löschen?', 'Aufgaben, Notizen, Chat, Freigaben und Verlauf werden unwiderruflich entfernt. Die Serververbindung bleibt erhalten.', [
      { text: 'Abbrechen', style: 'cancel' },
      { text: 'Alles löschen', style: 'destructive', onPress: () => resetStorage() }
    ]);
  }
  async function save() {
    if (busy) return;
    setBusy(true); setFeedback('');
    try {
      const result = await saveSettings(url.trim() || config?.url || '', token.trim() || config?.token || '');
      setUrl(''); setToken(''); setHealth(result); setFeedback('Verbindung erfolgreich eingerichtet.');
    } catch (e) { setFeedback(String(e.message || e)); }
    finally { setBusy(false); }
  }
  async function check() {
    setBusy(true); setFeedback('');
    try { const result = await request('/health'); setHealth(result); setFeedback('Serververbindung erfolgreich geprüft.'); }
    catch (e) { setFeedback(String(e.message || e)); }
    finally { setBusy(false); }
  }
  function confirmDisconnect() {
    Alert.alert('Serverzugang entfernen?', 'Die Serveradresse und das geschützte Zugangstoken werden vom Smartphone gelöscht. Lokale Aufgaben und Notizen bleiben erhalten.', [
      { text: 'Abbrechen', style: 'cancel' },
      { text: 'Entfernen', style: 'destructive', onPress: async () => {
        setBusy(true);
        try { await disconnect(); setHealth(null); setFeedback('Serverzugang entfernt.'); }
        catch (e) { setFeedback(String(e.message || e)); }
        finally { setBusy(false); }
      }}
    ]);
  }
  return <ScrollView style={{ flex: 1, backgroundColor: T.bg }} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.page}>
    <Heading subtitle="Version 1.2 · lokale Agenten und optionales KI-Gateway">Einstellungen</Heading>
    <Card>
      <Text style={styles.itemTitle}>Serververbindung</Text>
      <Muted style={{ marginTop: 8, marginBottom: 12 }}>Verbindung über HTTPS zu deinem eigenen AgentZentrale-Server. Das Zugangstoken wird verschlüsselt im Android Keystore abgelegt. Der KI-Anbieterschlüssel bleibt ausschließlich auf dem Server.</Muted>
      {loading ? <ActivityIndicator color={T.accent} /> : <Body style={{ color: connected ? T.accent : T.orange }}>{connected ? `Verbunden: ${config.url}` : 'Nicht verbunden'}</Body>}
      <Text style={{ color: T.muted, fontSize: 13, fontWeight: '700', marginTop: 14, marginBottom: 5 }}>Serveradresse (HTTPS)</Text>
      <TextInput accessibilityLabel="Serveradresse" value={url} onChangeText={setUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder={config?.url || 'https://agent.deinedomain.at'} placeholderTextColor={T.muted} style={[styles.input, { marginBottom: 12 }]}/>
      <Text style={{ color: T.muted, fontSize: 13, fontWeight: '700', marginBottom: 5 }}>Zugriffstoken (mind. 24 Zeichen)</Text>
      <TextInput accessibilityLabel="Server-Zugriffstoken" value={token} onChangeText={setToken} secureTextEntry autoCapitalize="none" autoCorrect={false} placeholder={connected ? 'Leer lassen, um bisherigen Schlüssel beizubehalten' : 'Server-Zugriffstoken'} placeholderTextColor={T.muted} style={[styles.input, { marginBottom: 11 }]}/>
      <ActionButton title={busy ? 'Verbinde …' : 'Verbinden / aktualisieren'} onPress={save} disabled={busy} icon="lock-closed-outline" />
      {connected ? <View style={{ gap: 9, marginTop: 10 }}>
        <ActionButton title="Verbindung prüfen" secondary disabled={busy} onPress={check} icon="pulse-outline" />
        <ActionButton title="Serverzugang entfernen" secondary disabled={busy} onPress={confirmDisconnect} icon="log-out-outline" />
      </View> : null}
      {feedback ? <Body style={{ marginTop: 11, color: feedback.toLowerCase().includes('erfolgreich') || feedback.includes('entfernt') ? T.accent : T.orange }}>{feedback}</Body> : null}
      {notice ? <Body style={{ color: T.red }}>{notice}</Body> : null}
      {health ? <View style={{ marginTop: 12, gap: 6 }}>
        <Body>KI: {health.aiEnabled ? 'serverbereit' : 'nicht konfiguriert'}</Body>
        <Body>GitHub lesen: {health.githubReadEnabled ? 'aktiv' : 'nicht verfügbar'}</Body>
        <Body>Entwurfs-PR erstellen: {health.githubWriteEnabled ? 'nach Freigabe möglich' : 'deaktiviert'}</Body>
      </View> : null}
    </Card>
    <Card>
      <Text style={styles.itemTitle}>Datenschutz und Freigaben</Text>
      <Body style={{ marginTop: 8 }}>Lokale Aufgaben, Notizen, Chatverläufe und das Aktionsprotokoll liegen auf dem Smartphone. Chatfragen und ausgewählte GitHub-Dateien werden nur bei einer aktiven Anfrage an deinen Server und gegebenenfalls an den KI-Anbieter übertragen.</Body>
      <Muted style={{ marginTop: 10 }}>Die Inhalte im AsyncStorage sind nicht zusätzlich Ende-zu-Ende-verschlüsselt. Keine Passwörter oder geheimen Daten in den Chat oder Notizen eingeben. GitHub-Pull-Requests werden nur nach Vorschau und gesonderter Freigabe erzeugt; sie werden niemals automatisch gemergt.</Muted>
    </Card>
    <Section>
      <Heading>Speicher</Heading>
      <Card>
        <Body>Aufgaben: {data.tasks.length} · Notizen: {data.notes.length}</Body>
        <Body>Chatnachrichten: {data.chat.length} · Freigaben: {data.approvals.length}</Body>
        <Body>Verlauf: {data.events.length}</Body>
        {storageError ? <Body style={{ color: T.red, marginTop: 10 }}>{storageError}</Body> : null}
        <ActionButton title="Alle lokalen Daten löschen" icon="trash-outline" danger style={{ marginTop: 18 }} onPress={confirmReset} />
      </Card>
    </Section>
  </ScrollView>;
}
