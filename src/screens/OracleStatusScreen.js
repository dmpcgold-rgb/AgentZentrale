import React,{useState,useCallback} from 'react';
import {ScrollView,RefreshControl} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import {useRemote} from '../store/RemoteContext';
import {ActionButton,Body,Card,Heading,Muted,styles} from '../components/Kit';
import {T} from '../theme';

export default function OracleStatusScreen(){
 const remote=useRemote();
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[host,setHost]=useState(null);
 const refresh=useCallback(async()=>{
  setBusy(true);setError('');
  try{const [report,status]=await Promise.allSettled([remote.request('/oracle/booking-report'),remote.request('/oracle/status')]);setData(report.status==='fulfilled'?report.value:null);setHost(status.status==='fulfilled'?status.value.status:null);if(report.status==='rejected')setError(report.reason.message);}
  catch(e){setHost(null);setData(null);setError(e.message);}
  finally{setBusy(false);}
 },[remote.request]);
 useFocusEffect(useCallback(()=>{if(remote.connected)refresh();},[remote.connected,refresh]));
 const report=data?.report;
 return <ScrollView style={{flex:1,backgroundColor:T.bg}} contentContainerStyle={styles.page}
 refreshControl={<RefreshControl refreshing={busy} onRefresh={refresh}/>}>
 <Heading subtitle="Oracle · WESTbahn">Live-Zentrale</Heading>
 <Card><Body>{remote.connected?'Serververbindung konfiguriert':'Server nicht verbunden'}</Body>
 <Muted>Bericht vom Server, kein zweiter Buchungsdienst.</Muted>
 <ActionButton title="Aktualisieren" secondary disabled={busy||!remote.connected} onPress={refresh}/>
 {error?<Body>{error}</Body>:null}</Card>
 <Card><Heading>Serverbetrieb</Heading>
 {host?<><Body>Automatik: {host.timer.enabled&&host.timer.active==='active'?'Aktiv':host.timer.active}</Body><Body>Buchungsdienst: {host.service.active}</Body><Muted>Nächster Lauf: {host.timer.next||'Unbekannt'}</Muted><Muted>Stand: {host.timestamp}</Muted></>:<Muted>Kein aktueller Host-Status verfügbar.</Muted>}
 </Card>
 {report?<><Card><Heading>Letzter Abschlussbericht</Heading>
 <Body>Bestätigt: {report.gesamt_bestaetigt}</Body>
 <Body>Lückenlos bis: {report.lueckenlos_bis||'Nicht bestätigt'}</Body>
 <Body>Ergebnis: {report.dienst_status}</Body>
 <Muted>Erstellt: {report.erstellt}</Muted>
 <Muted>Kein Echtzeitstatus des laufenden Dienstes.</Muted>
 </Card><Card><Heading>Neue Reservierungen</Heading>
 {report.neu_gebucht.map(d=><Body key={d}>{d}</Body>)}
 <Heading>Offene geprüfte Tage</Heading>
 {report.offene_gepruefte_tage.length?report.offene_gepruefte_tage.map(d=><Body key={d}>{d}</Body>):<Muted>Keine im letzten Bericht.</Muted>}
 </Card></>:<Card><Muted>Noch kein Serverbericht verfügbar.</Muted></Card>}
 </ScrollView>;
}
