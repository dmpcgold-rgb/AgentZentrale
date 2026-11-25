import React,{useState,useCallback} from 'react';
import {ScrollView,RefreshControl,Alert,TextInput} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import {useRemote} from '../store/RemoteContext';
import {ActionButton,Body,Card,Heading,Muted,styles} from '../components/Kit';
import {T} from '../theme';

export default function OracleStatusScreen(){
 const remote=useRemote();
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[host,setHost]=useState(null),[time,setTime]=useState('07:00'),[pending,setPending]=useState(null),[notice,setNotice]=useState('');
 const refresh=useCallback(async()=>{
  setBusy(true);setError('');
  try{const [report,status]=await Promise.allSettled([remote.request('/oracle/booking-report'),remote.request('/oracle/status')]);setData(report.status==='fulfilled'?report.value:null);setHost(status.status==='fulfilled'?status.value.status:null);if(report.status==='rejected')setError(report.reason.message);}
  catch(e){setHost(null);setData(null);setError(e.message);}
  finally{setBusy(false);}
 },[remote.request]);
 useFocusEffect(useCallback(()=>{if(remote.connected)refresh();},[remote.connected,refresh]));
 async function control(action){
  setBusy(true);setError('');setNotice('');
  try{const r=await remote.request('/oracle/control',{method:'POST',body:{action,time,confirm:'WESTBAHN-STEUERUNG'}});setPending(r.id);setNotice('Auftrag angenommen, Ausführung noch nicht bestätigt.');}
  catch(e){setError(e.message);}finally{setBusy(false);}
 }
 async function checkResult(){
  setBusy(true);
  try{const r=await remote.request('/oracle/control-result?id='+encodeURIComponent(pending));setNotice(r.status==='completed'?'Änderung bestätigt':r.status==='failed'?'Änderung fehlgeschlagen':'Auftrag noch offen');if(r.status!=='pending'){setPending(null);await refresh();}}
  catch(e){setError(e.message);}finally{setBusy(false);}
 }
 function confirm(action){Alert.alert('Automatik ändern',action==='pause'?'Zukünftige Läufe pausieren. Laufende Buchungen werden nicht abgebrochen.':action==='resume'?'Automatik fortsetzen. Ein verpasster Lauf kann nachgeholt werden.':'Montagszeit ändern auf '+time+' (Europe/Vienna).',[{text:'Abbrechen',style:'cancel'},{text:'Bestätigen',onPress:()=>control(action)}]);}
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
 <Muted>Telegram: {host?.telegramConfigured?'Konfiguriert (Versand hier nicht geprüft)':'Nicht bestätigt'}</Muted>
 <ActionButton title="Automatik pausieren" secondary disabled={!host||busy||!!pending||!host.timer.enabled} onPress={()=>confirm('pause')}/>
 <ActionButton title="Automatik fortsetzen" secondary disabled={!host||busy||!!pending||host.timer.enabled} onPress={()=>confirm('resume')}/>
 <Muted>Montagszeit (HH:MM, Wien)</Muted>
 <TextInput accessibilityLabel="Montagszeit" value={time} onChangeText={setTime} style={styles.input} maxLength={5}/>
 <ActionButton title="Zeitplan ändern" secondary disabled={!host?.timer.enabled||busy||!!pending||!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(time)} onPress={()=>confirm('schedule')}/>
 {notice?<Body>{notice}</Body>:null}
 {pending?<ActionButton title="Auftrag prüfen" secondary disabled={busy} onPress={checkResult}/>:null}
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
