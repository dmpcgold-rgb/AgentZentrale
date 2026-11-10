import { SafeAreaView } from 'react-native-safe-area-context';
import React, { useState } from 'react';
import { Alert, Keyboard, ScrollView, Text, TextInput, View, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { AGENTS } from '../core/engine';
import { useData } from '../store/DataContext';
import { T } from '../theme';
import { ActionButton, Body, Card, Heading, Muted, Section, styles } from '../components/Kit';

const examples = ['Aufgabe Rechnungen prüfen', 'Notiz Ideen für mein Projekt', 'Recherchiere Android Sicherheit', 'E-Mail Anfrage zum Angebot', 'Termin Besprechung am Freitag'];
export default function HubScreen({ navigation }) {
  const { data, submitCommand, apply, storageError } = useData();
  const [command, setCommand] = useState('');
  const [feedback, setFeedback] = useState(null);
  const openCount = data.tasks.filter(t => !t.done).length;
  const pendingCount = data.approvals.filter(a => a.status === 'pending').length;

  function submit() {
    const result = submitCommand(command);
    setFeedback(result);
    if (result.ok) { setCommand(''); Keyboard.dismiss(); }
  }
  function deleteNote(note) {
    Alert.alert('Notiz löschen?', note.content, [
      { text: 'Abbrechen', style: 'cancel' },
      { text: 'Löschen', style: 'destructive', onPress: () => apply({ type: 'DELETE_NOTE', id: note.id }) }
    ]);
  }

  return <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: T.bg }}>
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
        <View>
          <Text style={{ color: T.accent, fontWeight: '800', letterSpacing: 1.8, fontSize: 11 }}>DEINE AGENTEN-ZENTRALE</Text>
          <Text style={styles.pageTitle}>AgentZentrale</Text>
          <Muted>Lokale Aufgaben + optionaler KI-Server · V1.3</Muted>
        </View>
        <Pressable onPress={() => navigation.getParent()?.navigate('Einstellungen')} accessibilityRole="button" accessibilityLabel="Einstellungen öffnen" style={{ padding: 12, backgroundColor: T.surface, borderRadius: 15, minWidth: 48, minHeight: 48, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="settings-outline" color={T.text} size={24} />
        </Pressable>
      </View>

      {storageError ? <Card style={{ borderColor: T.red }}><Body style={{ color: T.red }}>{storageError}</Body></Card> : null}
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <Card style={{ flex: 1 }}><Muted>Offene Aufgaben</Muted><Text style={{ color: T.text, fontSize: 28, fontWeight: '900' }}>{openCount}</Text></Card>
        <Card style={{ flex: 1 }}><Muted>Freigaben</Muted><Text style={{ color: T.accent, fontSize: 28, fontWeight: '900' }}>{pendingCount}</Text></Card>
      </View>
      <Card style={{ marginTop: 4, borderColor: T.accent }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9, marginBottom: 8 }}>
          <Ionicons name="sparkles-outline" size={23} color={T.accent} />
          <Text style={styles.itemTitle}>Was soll ich erledigen?</Text>
        </View>
        <Muted style={{ marginBottom: 12 }}>Gib einen der unterstützten deutschen Befehle ein. Die App erklärt, was wirklich ausgeführt wird.</Muted>
        <TextInput
          value={command} onChangeText={setCommand} accessibilityLabel="Befehl für AgentZentrale"
          placeholder="z. B. Notiz Standplatz prüfen" placeholderTextColor={T.muted}
          multiline maxLength={1000} style={[styles.input, { minHeight: 96, textAlignVertical: 'top', marginBottom: 10 }]}
        />
        <ActionButton title="Befehl ausführen" icon="arrow-forward-circle-outline" onPress={submit} disabled={!command.trim()} />
        {feedback ? <View accessibilityLiveRegion="polite" style={{ marginTop: 11, padding: 10, borderRadius: 10, backgroundColor: T.surface2 }}>
          <Body style={{ color: feedback.ok ? T.accent : T.red }}>{feedback.message}</Body>
        </View> : null}
      </Card>

      <Section>
        <Heading subtitle="Verbinde dich mit spezialisierten Agenten">Online-Agenten</Heading>
        <View style={{ gap: 9 }}>
          <ActionButton title="KI-Chat öffnen" icon="chatbubbles-outline" onPress={() => navigation.navigate('KI')} />
          <ActionButton title="GitHub-Agent öffnen" secondary icon="code-slash-outline" onPress={() => navigation.navigate('GitHub')} />
          <ActionButton title="WESTbahn-Agent öffnen" secondary icon="train-outline" onPress={() => navigation.getParent()?.navigate('WESTbahn')} />
          <ActionButton title="Aktionsverlauf" secondary icon="time-outline" onPress={() => navigation.getParent()?.navigate('Verlauf')} />
        </View>
      </Section>
      <Section>
        <Heading subtitle="Antippen, um einen Beispielbefehl einzusetzen">Schnellbefehle</Heading>
        <View style={{ gap: 8 }}>
          {examples.map(ex => <Pressable key={ex} onPress={() => { setCommand(ex); setFeedback(null); }} accessibilityRole="button" accessibilityLabel={`Befehl einsetzen: ${ex}`} style={{ backgroundColor: T.surface2, padding: 13, borderRadius: 13, borderColor: T.line, borderWidth: 1, minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 9 }}>
            <Ionicons name="arrow-forward-outline" color={T.accent} size={17}/>
            <Text style={{ color: T.text, flex: 1 }}>{ex}</Text>
          </Pressable>)}
        </View>
      </Section>

      <Section>
        <Heading subtitle="Aktuelle Funktionen und geplante Erweiterungen">Spezialisierte Agenten</Heading>
        {AGENTS.map(agent => <Card key={agent.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ width: 42, height: 42, borderRadius: 13, backgroundColor: T.surface2, justifyContent: 'center', alignItems: 'center' }}>
            <Ionicons name={agent.icon} size={22} color={agent.active ? T.accent : T.muted}/>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.itemTitle}>{agent.name}</Text>
            <Muted>{agent.description}</Muted>
          </View>
          <Text style={{ color: agent.active ? T.accent : T.orange, fontSize: 12, fontWeight: '700' }}>{agent.active && ['ai','code'].includes(agent.id) ? 'Server' : agent.active ? 'Lokal' : 'Später'}</Text>
        </Card>)}
      </Section>

      <Section>
        <Heading subtitle="Nur lokal auf deinem Gerät">Deine letzten Notizen</Heading>
        {data.notes.length === 0 ? <Muted>Noch keine Notizen. Probiere „Notiz …“.</Muted> : data.notes.slice(0, 5).map(n => <Card key={n.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <Body style={{ flex: 1 }}>{n.content}</Body>
          <Pressable accessibilityRole="button" accessibilityLabel="Notiz löschen" onPress={() => deleteNote(n)} style={{ minHeight: 48, minWidth: 48, justifyContent: 'center', alignItems: 'center' }}><Ionicons name="trash-outline" color={T.red} size={19}/></Pressable>
        </Card>)}
      </Section>
    </ScrollView>
  </SafeAreaView>;
}
