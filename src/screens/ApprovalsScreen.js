import { SafeAreaView } from 'react-native-safe-area-context';
import React, { useState } from 'react';
import { Alert, FlatList, Linking, Share, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { previewApproval } from '../core/engine';
import { useData } from '../store/DataContext';
import { T } from '../theme';
import { ActionButton, Card, EmptyState, Muted, styles } from '../components/Kit';

export default function ApprovalsScreen() {
  const { data, apply } = useData();
  const [busy, setBusy] = useState(null);
  const pending = data.approvals.filter(a => a.status === 'pending');

  async function approve(item) {
    if (busy) return;
    setBusy(item.id);
    try {
      if (item.type === 'web-search') {
        const url = 'https://www.google.com/search?q=' + encodeURIComponent(item.payload);
        await Linking.openURL(url);
      } else if (item.type === 'mail-draft' || item.type === 'calendar-draft') {
        const result = await Share.share({ message: previewApproval(item), title: item.label });
        if (result.action === Share.dismissedAction) { setBusy(null); return; }
      } else {
        throw new Error('Aktionstyp wird nicht unterstützt.');
      }
      // The share sheet is only opened; this never asserts that an email was sent.
      apply({ type: 'FINISH_APPROVAL', id: item.id, status: 'approved' });
    } catch (error) {
      Alert.alert('Aktion nicht abgeschlossen', String(error?.message || error));
      apply({ type: 'FINISH_APPROVAL', id: item.id, status: 'failed' });
    } finally {
      setBusy(null);
    }
  }
  function reject(item) {
    Alert.alert('Aktion ablehnen?', item.label, [
      { text: 'Zurück', style: 'cancel' },
      { text: 'Ablehnen', style: 'destructive', onPress: () => apply({ type: 'FINISH_APPROVAL', id: item.id, status: 'rejected' }) }
    ]);
  }

  return <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: T.bg }}>
    <FlatList data={pending} keyExtractor={x => x.id} contentContainerStyle={[styles.page, { flexGrow: 1 }]}
      ListHeaderComponent={<View>
        <Text style={styles.pageTitle}>Freigaben</Text>
        <Muted style={{ marginBottom: 16 }}>Externe Aktionen starten nur nach deiner ausdrücklichen Freigabe. Entwürfe werden nicht automatisch versendet.</Muted>
      </View>}
      ListEmptyComponent={<EmptyState icon="shield-checkmark-outline" title="Alles geprüft" detail="Zurzeit sind keine Aktionen zur Freigabe offen." />}
      renderItem={({ item }) => <Card style={{ marginBottom: 14 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9, marginBottom: 8 }}>
          <Ionicons name={item.type === 'web-search' ? 'search-outline' : item.type === 'mail-draft' ? 'mail-outline' : 'calendar-outline'} size={22} color={T.orange}/>
          <Text style={[styles.itemTitle, { flex: 1 }]}>{item.label}</Text>
        </View>
        <View style={{ backgroundColor: T.surface2, borderRadius: 12, padding: 13, marginVertical: 10 }}>
          <Text style={{ color: T.text, lineHeight: 21, fontSize: 14 }}>{previewApproval(item)}</Text>
        </View>
        <Muted style={{ marginBottom: 12 }}>{item.type === 'web-search' ? 'Es wird nur eine Browser-Suche geöffnet.' : 'Es wird lediglich der Teilen-Dialog geöffnet; keine automatische Übermittlung.'}</Muted>
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <ActionButton style={{ flex: 1 }} secondary title="Ablehnen" onPress={() => reject(item)} disabled={busy === item.id} />
          <ActionButton style={{ flex: 1 }} title={busy === item.id ? 'Öffne …' : 'Freigeben'} onPress={() => approve(item)} disabled={busy !== null} />
        </View>
      </Card>}
    />
  </SafeAreaView>;
}
