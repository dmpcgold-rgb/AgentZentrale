import React from 'react';
import { Ionicons } from '@expo/vector-icons';
import { NavigationContainer, DarkTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { DataProvider } from './src/store/DataContext';
import { RemoteProvider } from './src/store/RemoteContext';
import ChatScreen from './src/screens/ChatScreen';
import GitHubScreen from './src/screens/GitHubScreen';
import { T } from './src/theme';
import HubScreen from './src/screens/HubScreen';
import WestbahnScreen from './src/screens/WestbahnScreen';
import TasksScreen from './src/screens/TasksScreen';
import ApprovalsScreen from './src/screens/ApprovalsScreen';
import HistoryScreen from './src/screens/HistoryScreen';
import SettingsScreen from './src/screens/SettingsScreen';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();
const icons = { Zentrale: 'grid-outline', KI: 'chatbubbles-outline', GitHub: 'logo-github', Aufgaben: 'checkbox-outline', Freigaben: 'shield-checkmark-outline' };
const appTheme = { ...DarkTheme, colors: { ...DarkTheme.colors, background: T.bg, card: T.surface, text: T.text, border: T.line, primary: T.accent } };

function Tabs() {
  return <Tab.Navigator screenOptions={({ route }) => ({
    headerShown: false,
    tabBarActiveTintColor: T.accent,
    tabBarInactiveTintColor: T.muted,
    tabBarLabelStyle: { fontSize: 11, fontWeight: '700' },
    tabBarItemStyle: { minHeight: 52 },
    tabBarStyle: { backgroundColor: T.surface, borderTopColor: T.line, height: 70, paddingTop: 8, paddingBottom: 10 },
    tabBarIcon: ({ color, size }) => <Ionicons name={icons[route.name]} size={size} color={color} />
  })}>
    <Tab.Screen name="Zentrale" component={HubScreen} />
    <Tab.Screen name="KI" component={ChatScreen} />
    <Tab.Screen name="GitHub" component={GitHubScreen} />
    <Tab.Screen name="Aufgaben" component={TasksScreen} />
    <Tab.Screen name="Freigaben" component={ApprovalsScreen} />
  </Tab.Navigator>;
}

export default function App() {
  return <SafeAreaProvider>
    <StatusBar style="light" />
    <DataProvider>
      <RemoteProvider>
      <NavigationContainer theme={appTheme}>
        <Stack.Navigator screenOptions={{ headerStyle: { backgroundColor: T.surface }, headerTintColor: T.text, contentStyle: { backgroundColor: T.bg } }}>
          <Stack.Screen name="Haupt" component={Tabs} options={{ headerShown: false }} />
          <Stack.Screen name="Einstellungen" component={SettingsScreen} />
          <Stack.Screen name="Verlauf" component={HistoryScreen} />
          <Stack.Screen name="WESTbahn" component={WestbahnScreen} />
        </Stack.Navigator>
      </NavigationContainer>
      </RemoteProvider>
    </DataProvider>
  </SafeAreaProvider>;
}
