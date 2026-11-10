import { SafeAreaView } from 'react-native-safe-area-context';
import React, { useState } from 'react';
import { Alert, FlatList, Text, TextInput, View, Pressable, Keyboard } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useData } from '../store/DataContext';
import { T } from '../theme';
import { ActionButton, Body, Card, EmptyState, Muted, styles } from '../components/Kit';

export default function TasksScreen() {
  const { data, submitCommand, apply } = useData();
  const [title, setTitle] = useState('');
  function add() {
    if (!title.trim()) return;
    submitCommand('Aufgabe ' + title.trim());
    setTitle(''); Keyboard.dismiss();
  }
  function remove(task) {
    Alert.alert('Aufgabe löschen?', task.title, [
      { text: 'Abbrechen', style: 'cancel' },
      { text: 'Endgültig löschen', style: 'destructive', onPress: () => apply({ type: 'DELETE_TASK', id: task.id }) }
    ]);
  }
  return <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: T.bg }}>
    <FlatList
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={[styles.page, { flexGrow: 1 }]}
      data={data.tasks} keyExtractor={item => item.id}
      ListHeaderComponent={<View>
        <Text style={styles.pageTitle}>Aufgaben</Text>
        <Muted style={{ marginBottom: 16 }}>Lokal gespeichert · {data.tasks.filter(t => !t.done).length} offen</Muted>
        <Card>
          <TextInput value={title} onChangeText={setTitle} placeholder="Neue Aufgabe …" placeholderTextColor={T.muted} accessibilityLabel="Neue Aufgabe" maxLength={1000} style={[styles.input, { marginBottom: 10 }]} returnKeyType="done" onSubmitEditing={add} />
          <ActionButton title="Aufgabe hinzufügen" onPress={add} icon="add-circle-outline" disabled={!title.trim()} />
        </Card>
      </View>}
      ListEmptyComponent={<EmptyState icon="checkbox-outline" title="Noch keine Aufgaben" detail="Lege deine erste Aufgabe an. Erinnerungsbenachrichtigungen sind noch nicht verfügbar." />}
      renderItem={({ item }) => <Card style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Pressable onPress={() => apply({ type: 'TOGGLE_TASK', id: item.id })} accessibilityRole="checkbox" accessibilityState={{ checked: item.done }} accessibilityLabel={`Aufgabe ${item.title}`} style={{ minWidth: 48, minHeight: 48, justifyContent: 'center', alignItems: 'center' }}>
          <Ionicons name={item.done ? 'checkmark-circle' : 'ellipse-outline'} color={item.done ? T.accent : T.muted} size={28}/>
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={[styles.itemTitle, item.done && { textDecorationLine: 'line-through', color: T.muted }]}>{item.title}</Text>
          <Muted>{item.done ? 'Erledigt' : 'Offen'}</Muted>
        </View>
        <Pressable onPress={() => remove(item)} accessibilityRole="button" accessibilityLabel={`Aufgabe ${item.title} löschen`} style={{ minWidth: 48, minHeight: 48, justifyContent: 'center', alignItems: 'center' }}>
          <Ionicons name="trash-outline" color={T.red} size={19} />
        </Pressable>
      </Card>}
    />
  </SafeAreaView>;
}
