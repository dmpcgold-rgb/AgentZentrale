import { SafeAreaView } from 'react-native-safe-area-context';
import React from 'react';
import { FlatList, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useData } from '../store/DataContext';
import { T } from '../theme';
import { Card, EmptyState, Muted, styles } from '../components/Kit';

function dateText(iso) {
  try { return new Intl.DateTimeFormat('de-AT', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(iso)); }
  catch { return iso; }
}
export default function HistoryScreen() {
  const { data } = useData();
  return <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: T.bg }}>
    <FlatList data={data.events} keyExtractor={x => x.id} contentContainerStyle={[styles.page, { flexGrow: 1 }]}
      ListHeaderComponent={<View><Text style={styles.pageTitle}>Verlauf</Text><Muted style={{ marginBottom: 16 }}>Lokales Protokoll der letzten 150 Aktionen</Muted></View>}
      ListEmptyComponent={<EmptyState icon="time-outline" title="Noch keine Aktionen" detail="Deine Befehle und Freigaben erscheinen hier." />}
      renderItem={({ item }) => <Card style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
        <Ionicons name="checkmark-circle-outline" color={T.accent} size={23}/>
        <View style={{ flex: 1 }}><Text style={styles.itemTitle}>{item.text}</Text><Muted>{dateText(item.at)}</Muted></View>
      </Card>}
    />
  </SafeAreaView>;
}
