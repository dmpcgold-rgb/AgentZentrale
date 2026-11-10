import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { T } from '../theme';

export function Card({ children, style }) {
  return <View style={[styles.card, style]}>{children}</View>;
}
export function Heading({ children, subtitle }) {
  return <View style={{ marginBottom: 12 }}>
    <Text style={styles.heading}>{children}</Text>
    {subtitle ? <Text style={styles.muted}>{subtitle}</Text> : null}
  </View>;
}
export function Body({ children, style }) {
  return <Text style={[styles.body, style]}>{children}</Text>;
}
export function Muted({ children, style }) {
  return <Text style={[styles.muted, style]}>{children}</Text>;
}
export function ActionButton({ title, onPress, icon, secondary = false, danger = false, disabled = false, style }) {
  return <Pressable
    accessibilityRole="button" accessibilityLabel={title}
    disabled={disabled} onPress={onPress}
    style={({ pressed }) => [styles.button, secondary && styles.secondary, danger && styles.danger, disabled && { opacity: .4 }, pressed && { opacity: .75 }, style]}
  >
    {icon ? <Ionicons name={icon} color={danger ? T.text : secondary ? T.text : T.accentText} size={19} /> : null}
    <Text style={[styles.buttonLabel, (secondary || danger) && { color: T.text }]}>{title}</Text>
  </Pressable>;
}
export function Section({ children, style }) {
  return <View style={[{ marginTop: 18 }, style]}>{children}</View>;
}
export function EmptyState({ icon, title, detail }) {
  return <Card style={{ alignItems: 'center', gap: 8, paddingVertical: 28 }}>
    <Ionicons name={icon} size={30} color={T.accent}/>
    <Text style={[styles.heading, { fontSize: 17 }]}>{title}</Text>
    <Muted style={{ textAlign: 'center' }}>{detail}</Muted>
  </Card>;
}
export function Screen({ children }) {
  return <View style={{ flex: 1, backgroundColor: T.bg }}>{children}</View>;
}
export const styles = StyleSheet.create({
  card: { backgroundColor: T.surface, borderRadius: T.radius, borderWidth: 1, borderColor: T.line, padding: 16, marginBottom: 10 },
  heading: { color: T.text, fontWeight: '800', fontSize: 20, marginBottom: 4 },
  body: { color: T.text, fontSize: 15, lineHeight: 23 },
  muted: { color: T.muted, fontSize: 13, lineHeight: 20 },
  button: { minHeight: 50, backgroundColor: T.accent, borderRadius: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, gap: 8 },
  secondary: { backgroundColor: T.surface2, borderWidth: 1, borderColor: T.line },
  danger: { backgroundColor: '#8A3037' },
  buttonLabel: { color: T.accentText, fontWeight: '800', fontSize: 15 },
  input: { backgroundColor: T.surface2, borderWidth: 1, borderColor: T.line, borderRadius: 14, color: T.text, padding: 15, fontSize: 15, minHeight: 52 },
  page: { paddingHorizontal: 17, paddingTop: 20, paddingBottom: 30 },
  pageTitle: { color: T.text, fontSize: 27, fontWeight: '900', marginBottom: 6 },
  itemTitle: { color: T.text, fontSize: 16, fontWeight: '700' }
});
