import React,{useState,useCallback,useRef,useEffect} from 'react';
import {ScrollView,RefreshControl,Alert,TextInput,View,Text,Pressable} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import {useRemote} from '../store/RemoteContext';
import {ActionButton,Body,Card,Heading,Muted,styles} from '../components/Kit';
import {T} from '../theme';


const dateKey=d=>d.toISOString().slice(0,10);
const monthLabel=d=>d.toLocaleDateString('de-AT',{month:'long',year:'numeric',timeZone:'UTC'});
function BookingCalendar({report,horizon,progress,saved,pendingDates,reservations}){
 const [offset,setOffset]=useState(0);
 const [selected,setSelected]=useState(null);
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Vienna',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(new Date());
 const part=k=>Number(parts.find(p=>p.type===k)?.value);
 const today=new Date(Date.UTC(part('year'),part('month')-1,part('day')));
 const months=Number.isInteger(horizon)&&horizon>=1&&horizon<=6?horizon:6;
 const lastMonth=new Date(Date.UTC(today.getUTCFullYear(),today.getUTCMonth()+months,1));
 const end=new Date(Date.UTC(lastMonth.getUTCFullYear(),lastMonth.getUTCMonth(),Math.min(today.getUTCDate(),new Date(Date.UTC(lastMonth.getUTCFullYear(),lastMonth.getUTCMonth()+1,0)).getUTCDate())));
 const index=Math.min(offset,months);
 const first=new Date(Date.UTC(today.getUTCFullYear(),today.getUTCMonth()+index,1));
 const count=new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth()+1,0)).getUTCDate();
 const leading=(first.getUTCDay()+6)%7;
 const booked=new Set([...(report?.bereits_gebucht||[]),...(report?.neu_gebucht||[]),...(progress?.confirmed||[]),...(progress?.newlyBooked||[]),...(saved||[])]);
 const open=new Set(report?.offene_gepruefte_tage||[]);
 const status=d=>{
  const key=dateKey(d);
  if(pendingDates?.includes(key))return ['Bestellung ungeklärt',T.orange,'#493622'];
  if(booked.has(key))return ['Bestätigt',T.green,'#183D35'];
  if(d.getUTCDay()===0||d.getUTCDay()===6)return ['Wochenende',T.muted,T.surface];
  if(d<today||d>end)return ['Außerhalb des Buchungsfensters',T.muted,T.surface];
  if(open.has(key))return ['Geprüft, nicht bestätigt',T.red,'#482831'];
  return ['Noch nicht bestätigt / unbekannt',T.orange,T.surface2];
 };
 const entries=Array.from({length:Math.ceil((leading+count)/7)*7},(_,i)=>{
  const day=i-leading+1;
  return day>=1&&day<=count?new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth(),day)):null;
 });
 const rows=Array.from({length:entries.length/7},(_,i)=>entries.slice(i*7,i*7+7));
 return <Card>
  <Heading subtitle="Serverspeicher, Bericht und aktueller Durchgang">Reservierungskalender</Heading>
  <Body>Zeitraum: {dateKey(today)} bis {dateKey(end)}</Body>
  <View style={{flexDirection:'row',alignItems:'center',justifyContent:'space-between',marginVertical:12}}>
   <Pressable accessibilityRole="button" accessibilityLabel="Vorheriger Monat" disabled={index===0} onPress={()=>{setOffset(index-1);setSelected(null);}} style={{minWidth:44,minHeight:44,alignItems:'center',justifyContent:'center',opacity:index===0?.35:1}}><Text style={{color:T.text,fontSize:24}}>‹</Text></Pressable>
   <Body style={{fontWeight:'800'}}>{monthLabel(first)}</Body>
   <Pressable accessibilityRole="button" accessibilityLabel="Nächster Monat" disabled={index>=months} onPress={()=>{setOffset(index+1);setSelected(null);}} style={{minWidth:44,minHeight:44,alignItems:'center',justifyContent:'center',opacity:index>=months?.35:1}}><Text style={{color:T.text,fontSize:24}}>›</Text></Pressable>
  </View>
  <View style={{flexDirection:'row'}}>{['Mo','Di','Mi','Do','Fr','Sa','So'].map(day=><Text key={day} style={{flex:1,textAlign:'center',color:T.muted,fontSize:12}}>{day}</Text>)}</View>
  {rows.map((row,i)=><View key={i} style={{flexDirection:'row',marginTop:3}}>{row.map((d,j)=>{
   if(!d)return <View key={j} style={{flex:1}}/>;
   const key=dateKey(d),[label,color,bg]=status(d);
   return <Pressable key={j} accessibilityRole="button" accessibilityLabel={key+' '+label} onPress={()=>setSelected({key,label})} style={{flex:1,minHeight:44,marginHorizontal:1,borderRadius:7,backgroundColor:bg,borderWidth:1,borderColor:selected?.key===key?T.accent:T.line,alignItems:'center',justifyContent:'center'}}><Text style={{color,fontWeight:'700'}}>{d.getUTCDate()}</Text><Text style={{color,fontSize:10}}>{label==='Bestätigt'?'✓':label==='Geprüft, nicht bestätigt'?'!':label==='Noch nicht bestätigt / unbekannt'?'?':'–'}</Text></Pressable>;
  })}</View>)}
  <View style={{marginTop:12,gap:5}}>
   <Body style={{color:T.green}}>✓ Bestätigte Reservierung</Body>
   <Body style={{color:T.red}}>! Geprüft, nicht bestätigt</Body>
   <Body style={{color:T.orange}}>? Unbekannt / noch nicht bestätigt</Body>
   <Muted>– Wochenende oder außerhalb des Buchungsfensters; ungeklärte Bestellungen bleiben gesperrt.</Muted>
   {selected?<Body>{selected.key}: {status(new Date(selected.key+'T00:00:00Z'))[0]}{reservations?.find(r=>r.date===selected.key)?.seat?' · Sitz '+reservations.find(r=>r.date===selected.key).seat:''}</Body>:null}
   <Muted>Keine Markierung ohne Nachweis. Ältere Berichte sind keine Garantie gegen spätere Stornierungen.</Muted>
   <Muted>Berichtsstand: {report?.erstellt||'Kein Bericht vorhanden'}</Muted>
  </View>
 </Card>;
}

export default function OracleStatusScreen(){
 const remote=useRemote();
 const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[host,setHost]=useState(null),[time,setTime]=useState('07:00'),[pending,setPending]=useState(null),[notice,setNotice]=useState('');
 const [months,setMonths]=useState('6');
 const pendingAction=useRef(null), sending=useRef(false), refreshing=useRef(false), checking=useRef(false);
 const refresh=useCallback(async()=>{
  if(refreshing.current||sending.current)return;
  refreshing.current=true;setBusy(true);setError('');
  try{const [report,status]=await Promise.allSettled([remote.request('/oracle/booking-report'),remote.request('/oracle/status')]);setData(report.status==='fulfilled'?report.value:null);setHost(status.status==='fulfilled'?status.value.status:null);if(status.status==='rejected')setError(status.reason.message);else if(report.status==='rejected')setError(report.reason.message);}
  catch(e){setHost(null);setData(null);setError(e.message);}
  finally{refreshing.current=false;setBusy(false);}
 },[remote.request]);
 useFocusEffect(useCallback(()=>{if(!remote.connected)return;refresh();const timer=setInterval(refresh,20000);return ()=>clearInterval(timer);},[remote.connected,refresh]));
 async function control(action){
  if(sending.current||pending)return;
  sending.current=true;pendingAction.current=action;setBusy(true);setError('');setNotice('');
  try{const r=await remote.request('/oracle/control',{method:'POST',body:{action,time,months:Number(months),confirm:'WESTBAHN-STEUERUNG'}});setPending(r.id);setNotice('Auftrag angenommen, Ausführung noch nicht bestätigt.');}
  catch(e){setError('Auftrag unklar: '+e.message+' — Serverstatus prüfen, nicht blind wiederholen.');}finally{sending.current=false;setBusy(false);}
 }
 async function checkResult(){
  if(!pending||checking.current)return;
  checking.current=true;
  try{const r=await remote.request('/oracle/control-result?id='+encodeURIComponent(pending));setNotice(r.status==='completed'?(pendingAction.current==='book_now'?'Startauftrag angenommen; Buchungsergebnis folgt im Bericht.':pendingAction.current==='stop_booking'?'Abbruch angefordert. Aktuelle Bestellung wird gegebenenfalls noch abgeglichen.':'Änderung bestätigt'):r.status==='failed'?'Änderung fehlgeschlagen':'Auftrag noch offen');if(r.status!=='pending'){setPending(null);await refresh();}}
  catch(e){setError(e.message);}finally{checking.current=false;}
 }
 useEffect(()=>{if(!pending)return;const timer=setInterval(checkResult,5000);return ()=>clearInterval(timer);},[pending,remote.request]);
 function confirm(action){Alert.alert('Automatik ändern',action==='stop_booking'?'Buchungslauf kontrolliert beenden? Eine bereits begonnene Bestellung wird noch abgeglichen. Bestehende Tickets und Wochenautomatik bleiben unverändert.':action==='book_now'?'Jetzt den bestehenden Buchungsdienst starten? Es gelten der gespeicherte Vorlauf und die bisherige Preisprüfung mit Restrisiko.':action==='horizon'?'Buchungsvorlauf auf '+months+' Monate setzen?':action==='pause'?'Zukünftige Läufe pausieren. Laufende Buchungen werden nicht abgebrochen.':action==='resume'?'Automatik fortsetzen. Ein verpasster Lauf kann nachgeholt werden.':'Montagszeit ändern auf '+time+' (Europe/Vienna).',[{text:'Abbrechen',style:'cancel'},{text:'Bestätigen',onPress:()=>control(action)}]);}
 const report=data?.report;
 const saved=host?.savedReservations;
 const savedSet=new Set(saved||[]);
 const [showSeats,setShowSeats]=useState(false);
 const [showHistory,setShowHistory]=useState(false);
 const nowParts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Vienna',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(new Date());
 const getPart=k=>Number(nowParts.find(p=>p.type===k)?.value);
 const start=new Date(Date.UTC(getPart('year'),getPart('month')-1,getPart('day')));
 const horizon=host?.monthsAhead;
 const endMonth=Number.isInteger(horizon)?new Date(Date.UTC(start.getUTCFullYear(),start.getUTCMonth()+horizon,1)):null;
 const end=endMonth?new Date(Date.UTC(endMonth.getUTCFullYear(),endMonth.getUTCMonth(),Math.min(start.getUTCDate(),new Date(Date.UTC(endMonth.getUTCFullYear(),endMonth.getUTCMonth()+1,0)).getUTCDate()))):null;
 const targets=[];
 if(end)for(let d=new Date(start);d<=end;d.setUTCDate(d.getUTCDate()+1)){if(d.getUTCDay()>0&&d.getUTCDay()<6)targets.push(dateKey(d));}
 const pendingDates=host?.pendingReservations;
 const effective=new Set([...(saved||[]),...(host?.progress?.confirmed||[]),...(host?.progress?.newlyBooked||[])]);
 const covered=targets.filter(d=>effective.has(d)&&!pendingDates?.includes(d)).length;
 const percent=targets.length&&Array.isArray(saved)?Math.round(covered/targets.length*100):null;
 const activityLabels={bulk:'Gmail-Sammelprüfung läuft',bulk_done:'Gmail-Sammelprüfung abgeschlossen',bulk_unclear:'Gmail-Sammelprüfung unvollständig',cache:'Reservierungsspeicher geladen',inventory:'Prüft WESTbahn-Ticketbestand',checkout:'Bestellvorgang gestartet',reconcile:'Prüft Bestellbestätigung',checking:'Prüft Reisetag',confirmed:'Bereits gebucht',new:'Neue Buchung bestätigt',retry:'Gmail-Abfrage wiederholen',stopped:'Buchung gestoppt – Bestätigung oder Prüfung unklar',skipped:'Prüfung unklar – übersprungen'};
 const stateLabel=s=>({active:'Aktiv',inactive:'Inaktiv',activating:'Läuft / startet',deactivating:'Wird beendet',failed:'Fehler'}[s]||s);
 const canStart=host&&Number.isInteger(host.monthsAhead)&&['inactive','failed'].includes(host.service.active)&&!busy&&!pending;
 return <ScrollView style={{flex:1,backgroundColor:T.bg}} contentContainerStyle={styles.page}
 refreshControl={<RefreshControl refreshing={busy} onRefresh={refresh}/>}>
 <Heading subtitle="Oracle · WESTbahn">Live-Zentrale</Heading>
 <Card><Heading>Agent-Aktivität</Heading>
 {(()=>{
  const running=['active','activating'].includes(host?.service?.active);
  const p=host?.progress;
  const labels={...activityLabels,checking:'Prüft Reservierung',confirmed:'Vorhandene Reservierung bestätigt',new:'Neue Reservierung bestätigt',retry:'Wiederholt Gmail-Abfrage',stopped:'Buchung gestoppt – Klärung erforderlich',skipped:'Tag übersprungen – Prüfung unklar'};
  const label=!host?'Serverstatus nicht verfügbar':running?(labels[p?.phase]||'Buchungsdienst läuft – aktueller Schritt noch nicht gemeldet'):pending?'Start- oder Steuerauftrag wartet auf Serverbestätigung':host.service.active==='failed'?'Letzter Buchungslauf mit Fehler beendet':host.service.active==='deactivating'?'Buchungsdienst wird beendet':'Bereit – wartet auf nächsten Auftrag';
  return <>
   <View style={{flexDirection:'row',alignItems:'center',gap:9,marginVertical:8}}><View style={{width:10,height:10,borderRadius:5,backgroundColor:!host||pending?T.orange:running?T.green:host.service.active==='failed'?T.red:T.muted}}/><Body style={{flex:1,fontWeight:'700'}}>{label}</Body></View>
   <Body style={{color:T.green}}>Gespeicherte Reservierungen: {Array.isArray(saved)?saved.length:'Noch nicht verfügbar'}</Body>
   {Array.isArray(saved)&&saved.length?<Muted>Letzter gespeicherter Reisetag: {[...saved].sort().at(-1)} (kein Nachweis für Lückenlosigkeit)</Muted>:null}
   {running&&p?.currentDay?<Body>Reisetag: {p.currentDay}</Body>:null}
   {running&&p?<><Body>Bestätigt: {p.confirmed.length} · Neu: {p.newlyBooked.length}</Body><Muted>Fortschrittsdaten abgerufen: {p.updatedAt?new Date(p.updatedAt).toLocaleString('de-AT'): 'Unbekannt'}</Muted></>:null}
   <Heading>Aktivitätsprotokoll</Heading>
   {p?.events?.length?p.events.slice(-12).reverse().map((e,i)=><View key={i} style={{borderBottomWidth:1,borderColor:T.line,paddingVertical:6}}><Body>{activityLabels[e.phase]||e.phase}{e.day?' · '+e.day:''}{e.count!=null?' · '+e.count:''}</Body></View>):<Muted>Noch keine Protokolleinträge vom Server verfügbar.</Muted>}
   {pending?<Muted>Auftrag noch nicht bestätigt. Nicht erneut starten.</Muted>:null}
   {!running&&!pending&&host?.timer?.next?<Muted>Nächster automatischer Lauf: {host.timer.next}</Muted>:null}
   <Muted>Serverstatus: {host?.timestamp?new Date(host.timestamp).toLocaleString('de-AT'):'Nicht verfügbar'} · Aktualisierung alle 20 Sekunden</Muted>
  </>;
 })()}
 </Card>
 <Card><Heading>Buchungsziel</Heading>
 {percent!==null?<><Body style={{fontWeight:'800',fontSize:24,color:T.green}}>{percent}%</Body><View style={{height:10,borderRadius:5,backgroundColor:T.surface2,overflow:'hidden'}}><View style={{height:10,width:percent+'%',backgroundColor:T.accent}}/></View><Body>{covered} von {targets.length} Werktagen (Mo–Fr) bestätigt</Body><Muted>Ziel bis {dateKey(end)} · Feiertage wie bisher eingeschlossen.</Muted></>:<Muted>Serverdaten für Fortschritt fehlen.</Muted>}
 <Body style={{color:T.orange}}>Ungeklärte Bestellungen: {Array.isArray(pendingDates)?pendingDates.length:'Nicht verfügbar'}</Body>
 {pendingDates?.map(d=><Muted key={d}>{d} · Keine automatische Wiederholung</Muted>)}
 <Muted>Gespeicherte Nachweise können spätere Stornierungen nicht ausschließen.</Muted></Card>
 <Card><Heading>Reservierungen und Sitzplätze</Heading>
 <ActionButton secondary title={showSeats?'Übersicht einklappen':'Sitzplatzübersicht öffnen'} onPress={()=>setShowSeats(!showSeats)}/>
 {showSeats?(Array.isArray(saved)?saved.map(d=>{const r=host?.reservations?.find(x=>x.date===d);return <View key={d} style={{borderBottomWidth:1,borderColor:T.line,paddingVertical:6}}><Body>{d} · {r?.seat?'Sitz '+r.seat:'Sitz unbekannt'}</Body><Muted>{r?.source==='manual_westbahn_verification'?'Manuell bestätigt':r?.source==='official_email'?'Gmail-Nachweis':'Gespeicherter Nachweis'} · Wagen nicht verifiziert</Muted></View>}):<Muted>Serverspeicher nicht verfügbar.</Muted>):null}</Card>
 <Card><Heading>Buchungsverlauf und Sicherung</Heading>
 <Muted>Letzte Sicherung: {host?.backupAt||'Nicht gemeldet'}</Muted>
 <ActionButton secondary title={showHistory?'Verlauf einklappen':'Buchungsverlauf öffnen'} onPress={()=>setShowHistory(!showHistory)}/>
 {showHistory?(host?.history?.length?host.history.map((r,i)=><View key={i} style={{paddingVertical:8,borderBottomWidth:1,borderColor:T.line}}><Body>{new Date(r.erstellt).toLocaleString('de-AT')}</Body><Body>{r.dienst_status==='success'?'Beendet':r.dienst_status==='signal'?'Unterbrochen':'Mit Fehler / offen beendet'} · {r.gesamt_bestaetigt??'?'} bestätigt</Body><Muted>Neu: {r.neu_gebucht.length} · Offen: {r.offene_gepruefte_tage.length}</Muted></View>):<Muted>Keine historischen Berichte verfügbar.</Muted>):null}</Card>
 <Card><Body>{remote.connected?'Serververbindung konfiguriert':'Server nicht verbunden'}</Body>
 <Muted>Bericht vom Server, kein zweiter Buchungsdienst.</Muted>
 <ActionButton title="Aktualisieren" secondary disabled={busy||!remote.connected} onPress={refresh}/>
 {error?<Body>{error}</Body>:null}</Card>
 <Card><Heading>Serverbetrieb</Heading>
 {host?<><Body>Automatik: {host.timer.enabled&&host.timer.active==='active'?'Aktiv':stateLabel(host.timer.active)}</Body><Body>Buchungsdienst: {stateLabel(host.service.active)}</Body><Muted>Nächster Lauf: {host.timer.next||'Unbekannt'}</Muted><Muted>Stand: {host.timestamp}</Muted></>:<Muted>Kein aktueller Host-Status verfügbar.</Muted>}
 <Muted>Telegram: {host?.telegramConfigured?'Konfiguriert (Versand hier nicht geprüft)':'Nicht bestätigt'}</Muted>
 <ActionButton title="Automatik pausieren" secondary disabled={!host||busy||!!pending||!host.timer.enabled} onPress={()=>confirm('pause')}/>
 <ActionButton title="Automatik fortsetzen" secondary disabled={!host||busy||!!pending||host.timer.enabled} onPress={()=>confirm('resume')}/>
 <Heading>Buchungsvorlauf</Heading>
 <Body>Gespeichert: {host?.monthsAhead??'Unbekannt'} Monate</Body>
 <Muted>Rollierender Vorlauf (1 bis 6 Monate, soweit verfügbar)</Muted>
 <TextInput accessibilityLabel="Buchungsvorlauf in Monaten" value={months} onChangeText={setMonths} keyboardType="number-pad" style={styles.input} maxLength={1}/>
 <ActionButton title="Buchungsvorlauf speichern" secondary disabled={!host||busy||!!pending||!(/^[1-6]$/).test(months)} onPress={()=>confirm('horizon')}/>
 <ActionButton title="Jetzt maximal vorausbuchen" disabled={!canStart} onPress={()=>confirm('book_now')}/>
 <ActionButton title="Buchungslauf abbrechen" danger disabled={!host||!["active","activating"].includes(host.service.active)||!!pending||busy} onPress={()=>confirm("stop_booking")}/>
 <Muted>Beendet den aktuellen Lauf kontrolliert; bereits begonnene Bestellungen werden noch abgeglichen. Keine Ticketstornierung.</Muted>
 <Muted>Der Startauftrag ist keine Buchungsbestätigung. Der Wochenplan bleibt unverändert.</Muted>
 <Muted>Montagszeit (HH:MM, Wien)</Muted>
 <TextInput accessibilityLabel="Montagszeit" value={time} onChangeText={setTime} style={styles.input} maxLength={5}/>
 <ActionButton title="Zeitplan ändern" secondary disabled={!host?.timer.enabled||busy||!!pending||!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(time)} onPress={()=>confirm('schedule')}/>
 {notice?<Body>{notice}</Body>:null}
 {pending?<ActionButton title="Auftrag prüfen" secondary disabled={busy} onPress={checkResult}/>:null}
 </Card>
 <Card><Heading subtitle="Aktueller Durchgang · Oracle">Live-Buchungsfortschritt</Heading>
 {host?.progress&&['active','activating'].includes(host.service.active)?<>
 <Body>Aktueller Reisetag: {host.progress.currentDay||'Noch nicht bekannt'}</Body>
 <Body>Verarbeitung: {({...activityLabels,checking:'Reservierung prüfen',confirmed:'Bereits gebucht',new:'Neue Buchung bestätigt',retry:'Gmail erneut prüfen',stopped:'Prüfung gestoppt',skipped:'Tag übersprungen'})[host.progress.phase]||'Unbekannt'}</Body>
 <Body style={{color:T.green}}>Bestätigte Tage: {host.progress.confirmed.length}</Body>
 <Body>Davon neu gebucht: {host.progress.newlyBooked.length}</Body>
 <Muted>Stand: {host.progress.updatedAt||'Unbekannt'}</Muted>
 </>:<Muted>{host&&['active','activating'].includes(host.service.active)?'Buchungslauf aktiv. Noch keine Live-Fortschrittsdaten verfügbar.':'Kein aktiver Buchungslauf.'}</Muted>}
 <Muted>Aktualisierung alle 20 Sekunden. Nur nachgewiesene Reservierungen werden gezählt.</Muted>
 </Card>
 <BookingCalendar pendingDates={pendingDates} reservations={host?.reservations} saved={saved} report={report} horizon={host?.monthsAhead} progress={['active','activating'].includes(host?.service?.active)?host?.progress:null}/>
 {report?<><Card><Heading>Letzter Abschlussbericht</Heading>
 <Body>Bestätigt: {report.gesamt_bestaetigt}</Body>
 <Body>Lückenlos bis: {report.lueckenlos_bis||'Nicht bestätigt'}</Body>
 <Body>Ergebnis: {report.dienst_status}</Body>
 <Muted>Erstellt: {report.erstellt}</Muted>
 <Muted>Kein Echtzeitstatus des laufenden Dienstes.</Muted>
 </Card><Card><Heading>Neue Reservierungen</Heading>
 {report.neu_gebucht.map(d=><Body key={d}>{d}</Body>)}
 <Heading>Offene geprüfte Tage</Heading>
 {report.offene_gepruefte_tage.length?report.offene_gepruefte_tage.map(d=><Body key={d}>{d}{savedSet.has(d)?' · später im Speicher bestätigt':''}</Body>):<Muted>Keine im letzten Bericht.</Muted>}
 </Card></>:<Card><Muted>Noch kein Serverbericht verfügbar.</Muted></Card>}
 </ScrollView>;
}
