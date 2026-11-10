import React, { useRef, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useData } from '../store/DataContext';
import { useRemote } from '../store/RemoteContext';
import { T } from '../theme';
import { ActionButton, Body, Card, Muted, styles } from '../components/Kit';

const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`;
export default function ChatScreen({ navigation }) {
  const { data, apply } = useData();
  const { connected, request, loading: configLoading } = useRemote();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const listRef = useRef(null);
  async function send() {
    const message = text.trim();
    if (!message || busy || !connected) return;
    const history = data.chat.slice(-8).map(m => ({ role: m.role, content: m.content }));
    apply({ type: 'CHAT_MESSAGE', id: uid(), role: 'user', content: message });
    setText(''); setBusy(true); setError('');
    try {
      const response = await request('/chat', { method: 'POST', body: { message, history } });
      if (!response.answer || typeof response.answer !== 'string') throw new Error('Keine verwertbare KI-Antwort empfangen.');
      apply({ type: 'CHAT_MESSAGE', id: uid(), role: 'assistant', content: response.answer });
    } catch (e) { setError(String(e.message || e)); }
    finally { setBusy(false); }
  }
  function clearHistory() {
    Alert.alert('Chatverlauf löschen?', 'Alle lokal gespeicherten KI-Nachrichten werden gelöscht.', [
      { text: 'Abbrechen', style: 'cancel' },
      { text: 'Löschen', style: 'destructive', onPress: () => apply({ type: 'CLEAR_CHAT' }) }
    ]);
  }
  return <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: T.bg }}>
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={{ paddingHorizontal: 17, paddingTop: 17, paddingBottom: 10, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flex: 1 }}><Text style={styles.pageTitle}>KI-Assistent</Text><Muted>{connected ? 'Online über deinen privaten Server' : 'Noch nicht verbunden'}</Muted></View>
        <Pressable onPress={clearHistory} accessibilityRole="button" accessibilityLabel="Chatverlauf löschen" style={{ minWidth: 48, minHeight: 48, justifyContent: 'center', alignItems: 'center' }}><Ionicons name="trash-outline" color={T.muted} size={22}/></Pressable>
      </View>
      {!connected && !configLoading ? <Card style={{ marginHorizontal: 17 }}>
        <Body>Der KI-Chat benötigt eine HTTPS-Serveradresse und einen Zugriffsschlüssel.</Body>
        <Muted style={{ marginTop: 9, marginBottom: 14 }}>API-Schlüssel für den KI-Anbieter bleiben auf deinem Server.</Muted>
        <ActionButton title="Server einrichten" icon="settings-outline" onPress={() => navigation.getParent()?.navigate('Einstellungen')} />
      </Card> : null}
      <ScrollView ref={listRef} contentContainerStyle={{ flexGrow: 1, padding: 17, gap: 12 }} onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })} keyboardShouldPersistTaps="handled">
        {data.chat.length === 0 ? <View style={{ justifyContent: 'center', alignItems: 'center', flex: 1, gap: 12, padding: 20 }}>
          <Ionicons name="chatbubbles-outline" color={T.accent} size={48}/>
          <Text style={{ color: T.text, fontSize: 17, fontWeight: '800', textAlign: 'center' }}>Stelle dem KI-Assistenten eine Frage</Text>
          <Muted style={{ textAlign: 'center' }}>Antworten sind Text. Der Chat darf keine E-Mails senden, Käufe durchführen oder GitHub-Dateien verändern.</Muted>
        </View> : data.chat.map(m => <View key={m.id} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', backgroundColor: m.role === 'user' ? T.surface2 : T.surface, borderColor: m.role === 'assistant' ? T.accent : T.line, borderWidth: 1, borderRadius: 16, padding: 13, maxWidth: '94%' }}>
          <Text style={{ color: m.role === 'user' ? T.accent : T.orange, fontSize: 11, fontWeight: '800', marginBottom: 6 }}>{m.role === 'user' ? 'DU' : 'KI-ASSISTENT'}</Text>
          <Body>{m.content}</Body>
        </View>)}
        {busy ? <View style={{ flexDirection: 'row', gap: 9, alignItems: 'center' }}><ActivityIndicator color={T.accent}/><Muted>KI antwortet …</Muted></View> : null}
        {error ? <Card style={{ borderColor: T.red }}><Body style={{ color: T.red }}>{error}</Body><Muted>Nachricht ist lokal gespeichert. Die Anfrage wurde nicht erfolgreich abgeschlossen.</Muted></Card> : null}
      </ScrollView>
      <View style={{ backgroundColor: T.surface, borderTopWidth: 1, borderTopColor: T.line, paddingHorizontal: 15, paddingTop: 10, paddingBottom: 10 }}>
        <TextInput accessibilityLabel="Nachricht an KI-Assistenten" value={text} onChangeText={setText} editable={!busy && connected}
          placeholder="Frage eingeben …" placeholderTextColor={T.muted} multiline maxLength={4000}
          style={[styles.input, { maxHeight: 110, textAlignVertical: 'top', marginBottom: 9 }]}/>
        <ActionButton title={busy ? 'Antwort wird geladen' : 'An KI senden'} icon="send-outline" onPress={send} disabled={!connected || busy || !text.trim()} />
      </View>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}
