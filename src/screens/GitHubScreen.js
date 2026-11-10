import React, { useState } from 'react';
import { ActivityIndicator, Alert, Linking, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRemote } from '../store/RemoteContext';
import { useData } from '../store/DataContext';
import { qs } from '../api/client';
import { T } from '../theme';
import { ActionButton, Body, Card, Heading, Muted, Section, styles } from '../components/Kit';

function Field({ label, value, onChangeText, placeholder, multiline=false, maxLength=150 }) {
  return <View style={{ gap: 6, marginBottom: 10 }}>
    <Text style={{ color: T.muted, fontSize: 13, fontWeight: '700' }}>{label}</Text>
    <TextInput accessibilityLabel={label} value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor={T.muted} autoCapitalize="none" autoCorrect={false} multiline={multiline} maxLength={maxLength} style={[styles.input, multiline && { minHeight: 95, textAlignVertical: 'top' }]}/>
  </View>;
}
export default function GitHubScreen({ navigation }) {
  const { connected, request } = useRemote();
  const { apply } = useData();
  const [owner, setOwner] = useState('dmpcgold-rgb');
  const [repo, setRepo] = useState('');
  const [path, setPath] = useState('');
  const [dir, setDir] = useState('');
  const [repos, setRepos] = useState([]);
  const [entries, setEntries] = useState([]);
  const [file, setFile] = useState(null);
  const [instruction, setInstruction] = useState('');
  const [proposal, setProposal] = useState(null);
  const [showOriginal, setShowOriginal] = useState(false);
  const [pr, setPr] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  async function job(name, run) {
    if (busy || !connected) return;
    setBusy(name); setError('');
    try { await run(); } catch (e) { setError(String(e?.message || e)); }
    finally { setBusy(''); }
  }
  function changeTarget(value, setter) { setter(value); setFile(null); setProposal(null); setPr(null); setEntries([]); }
  const browseRepos = () => job('repos', async () => {
    const x = await request('/github/repos' + qs({ owner }));
    setRepos(x.repos || []); setRepo(''); setEntries([]); setFile(null); setProposal(null);
  });
  const browseDir = (targetRepo = repo, targetDir = '') => job('folder', async () => {
    const x = await request('/github/entries' + qs({ owner, repo: targetRepo, path: targetDir }));
    setRepo(targetRepo); setDir(targetDir); setEntries(x.items || []); setFile(null); setProposal(null); setPr(null);
  });
  const openFile = (targetPath = path) => job('file', async () => {
    const x = await request('/github/file' + qs({ owner, repo, path: targetPath }));
    setPath(targetPath); setFile(x); setProposal(null); setPr(null);
  });
  const propose = () => job('proposal', async () => {
    const x = await request('/github/proposals', { method: 'POST', body: { owner, repo, path: file?.path || path, instruction } });
    setProposal(x); setShowOriginal(false); setPr(null);
    apply({ type: 'LOG_ACTIVITY', text: `GitHub-Änderungsvorschlag vorbereitet: ${owner}/${repo}/${x.path}` });
  });
  const createPR = () => Alert.alert('Entwurfs-Pull-Request erstellen?', `Repository: ${owner}/${repo}\nDatei: ${proposal?.path}\n\nDie Änderung wird auf einen NEUEN Branch geschrieben. Dein Hauptzweig bleibt unverändert. Vor einem Merge bitte den Code testen.`, [
    { text: 'Abbrechen', style: 'cancel' },
    { text: 'Freigeben', onPress: () => job('pr', async () => {
      const result = await request('/github/create-pr', { method: 'POST', body: { id: proposal.id, confirm: 'FREIGEBEN' } });
      setPr(result); setProposal(null);
      apply({ type: 'LOG_ACTIVITY', text: `GitHub-Entwurfs-PR #${result.number} erstellt: ${owner}/${repo}` });
    }) }
  ]);

  return <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: T.bg }}>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.page}>
      <Text style={styles.pageTitle}>GitHub-Agent</Text>
      <Muted style={{ marginBottom: 15 }}>Repositories lesen, Dateien prüfen und Änderungen als Entwurfs-PR vorschlagen – niemals automatisch mergen.</Muted>
      {!connected ? <Card>
        <Body>Verbinde zuerst deinen privaten AgentZentrale-Server.</Body>
        <ActionButton title="Server einrichten" icon="settings-outline" style={{ marginTop: 12 }} onPress={() => navigation.getParent()?.navigate('Einstellungen')}/>
      </Card> : null}
      {error ? <Card style={{ borderColor: T.red }}><Body style={{ color: T.red }}>{error}</Body></Card> : null}
      {busy ? <View style={{ paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }}><ActivityIndicator color={T.accent}/><Muted>{busy === 'proposal' ? 'KI erstellt einen Änderungsvorschlag …' : busy === 'pr' ? 'Erstelle Entwurfs-Pull-Request …' : 'Lade GitHub-Daten …'}</Muted></View> : null}
      <Card>
        <Heading>1. Repository wählen</Heading>
        <Field label="GitHub-Konto" value={owner} onChangeText={v => changeTarget(v, setOwner)} placeholder="Konto oder Organisation"/>
        <ActionButton title="Repositories anzeigen" onPress={browseRepos} disabled={!connected || !!busy || !owner.trim()} secondary icon="folder-open-outline"/>
        {repos.length ? <View style={{ marginTop: 12, gap: 7 }}>{repos.map(r => <Pressable key={r.name} accessibilityRole="button" accessibilityLabel={`Repository ${r.name} öffnen`} onPress={() => browseDir(r.name)} style={{ backgroundColor: T.surface2, padding: 12, minHeight: 48, borderRadius: 10, flexDirection: 'row', alignItems: 'center', gap: 9 }}>
          <Ionicons name="folder-outline" color={T.accent} size={21}/><Text style={{ color: T.text, flex: 1 }}>{r.name}</Text><Ionicons name="chevron-forward-outline" color={T.muted} size={19}/>
        </Pressable>)}</View> : null}
        <Muted style={{ marginTop: 8 }}>Private Repositories erscheinen ggf. nicht in der öffentlichen Liste. Sie können direkt eingegeben werden, sofern der Server Zugriff hat.</Muted>
        <Field label="Repository (direkte Eingabe möglich)" value={repo} onChangeText={v => changeTarget(v, setRepo)} placeholder="z. B. Gym-Coach"/>
        <ActionButton title="Dateien öffnen" secondary onPress={() => browseDir(repo)} disabled={!connected || !!busy || !repo.trim()} icon="folder-outline" />
      </Card>
      {repo ? <Card>
        <Heading subtitle={`${owner}/${repo}${dir ? '/' + dir : ''}`}>2. Datei wählen</Heading>
        {dir ? <ActionButton title="Eine Ebene zurück" secondary onPress={() => browseDir(repo, dir.includes('/') ? dir.substring(0, dir.lastIndexOf('/')) : '')} disabled={!!busy} icon="arrow-up-outline" style={{ marginBottom: 9 }}/> : null}
        {entries.map(entry => <Pressable key={entry.path} onPress={() => entry.type === 'dir' ? browseDir(repo, entry.path) : openFile(entry.path)} accessibilityRole="button" accessibilityLabel={`${entry.type === 'dir' ? 'Ordner' : 'Datei'} ${entry.name} öffnen`} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, borderBottomWidth: 1, borderBottomColor: T.line, paddingVertical: 11, minHeight: 48 }}>
          <Ionicons name={entry.type === 'dir' ? 'folder' : 'document-text-outline'} color={entry.type === 'dir' ? T.orange : T.accent} size={21}/>
          <Body style={{ flex: 1 }}>{entry.name}</Body><Ionicons name="chevron-forward" color={T.muted} size={17}/>
        </Pressable>)}
        <Field label="Dateipfad (oder oben auswählen)" value={path} onChangeText={v => changeTarget(v, setPath)} placeholder="z. B. App.js" maxLength={300}/>
        <ActionButton title="Datei lesen" secondary icon="eye-outline" onPress={() => openFile(path)} disabled={!connected || !!busy || !path.trim()}/>
      </Card> : null}
      {file ? <Card>
        <Heading subtitle={file.path}>3. Datei prüfen</Heading>
        <ScrollView nestedScrollEnabled style={{ maxHeight: 260, borderRadius: 12, backgroundColor: T.surface2, padding: 11 }}><Text selectable style={{ color: T.text, fontFamily: 'monospace', fontSize: 12, lineHeight: 18 }}>{file.content}</Text></ScrollView>
        <Muted style={{ marginTop: 9, marginBottom: 12 }}>Inhalt wird nur angezeigt. Keine Änderung gespeichert.</Muted>
        <Muted style={{ marginBottom: 9 }}>Beim Erstellen eines KI-Vorschlags wird der angezeigte Dateiinhalt an deinen Server und an den konfigurierten KI-Anbieter übertragen.</Muted>
        <Field label="Was soll die KI an dieser Datei verbessern?" value={instruction} onChangeText={setInstruction} placeholder="Beschreibe eine konkrete Änderung" multiline maxLength={1800}/>
        <ActionButton title="Änderung vorschlagen" icon="sparkles-outline" onPress={propose} disabled={!connected || !!busy || !instruction.trim()}/>
      </Card> : null}
      {proposal ? <Card style={{ borderColor: T.accent }}>
        <Heading subtitle="Noch NICHT auf GitHub geschrieben">4. Änderungsvorschau</Heading>
        <Body style={{ fontWeight: '800' }}>{proposal.title}</Body>
        <Muted style={{ marginVertical: 10 }}>{proposal.summary}</Muted>
        <Muted>Pfad: {proposal.path} · Gültig für 10 Minuten</Muted>
        <Pressable accessibilityRole="button" onPress={() => setShowOriginal(v => !v)} style={{ minHeight: 48, justifyContent: 'center' }}><Text style={{ color: T.accent, fontWeight: '700' }}>{showOriginal ? 'Geänderte Datei zeigen' : 'Originaldatei zeigen'}</Text></Pressable>
        <ScrollView nestedScrollEnabled style={{ maxHeight: 320, backgroundColor: T.surface2, padding: 10, borderRadius: 10 }}><Text selectable style={{ color: T.text, fontFamily: 'monospace', fontSize: 12, lineHeight: 18 }}>{showOriginal ? proposal.original : proposal.proposed}</Text></ScrollView>
        <Muted style={{ marginVertical: 14 }}>Prüfe den gesamten Vorschlag. Diese Version führt keine automatischen Tests des geänderten Repositories aus.</Muted>
        <ActionButton title="Vorschlag verwerfen" secondary onPress={() => setProposal(null)} disabled={!!busy} style={{ marginBottom: 9 }}/>
        <ActionButton title="Entwurfs-PR nach Freigabe erstellen" icon="git-pull-request-outline" disabled={!proposal.githubWriteEnabled || !!busy} onPress={createPR}/>
        {!proposal.githubWriteEnabled ? <Muted style={{ marginTop: 8 }}>GitHub-Schreibzugriff ist auf deinem Server deaktiviert. Ein Pull Request kann derzeit nicht erstellt werden.</Muted> : null}
      </Card> : null}
      {pr ? <Card style={{ borderColor: T.accent }}>
        <Heading>Pull Request vorbereitet</Heading><Body>{pr.message}</Body>
        <ActionButton title={`Pull Request #${pr.number} in GitHub öffnen`} icon="open-outline" style={{ marginTop: 12 }} onPress={() => { if (typeof pr.url === 'string' && pr.url.startsWith('https://github.com/')) Linking.openURL(pr.url); }}/>
      </Card> : null}
    </ScrollView>
  </SafeAreaView>;
}
