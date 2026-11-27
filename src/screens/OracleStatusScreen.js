import React,{useState,useCallback,useRef,useEffect} from 'react';
import {ScrollView,RefreshControl,Alert,TextInput,View,Text,Pressable} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import {useRemote} from '../store/RemoteContext';
import {ActionButton,Body,Card,Heading,Muted,styles} from '../components/Kit';
import {T} from '../theme';


const dateKey=d=>d.toISOString().slice(0,10);
const monthLabel=d=>d.toLocaleDateString('de-AT',{month:'long',year:'numeric',timeZone:'UTC'});
function BookingCalendar({report,horizon,weeks,progress,saved,pendingDates,reservations}){
 const [offset,setOffset]=useState(0);
 const [selected,setSelected]=useState(null);
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Vienna',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(new Date());
 const part=k=>Number(parts.find(p=>p.type===k)?.value);
 const today=new Date(Date.UTC(part('year'),part('month')-1,part('day')));
 const months=Number.isInteger(horizon)&&horizon>=1&&horizon<=6?horizon:6;
 const lastMonth=new Date(Date.UTC(today.getUTCFullYear(),today.getUTCMonth()+months,1));
 const end=weeks?new Date(today.getTime()+weeks*7*86400000):new Date(Date.UTC(lastMonth.getUTCFullYear(),lastMonth.getUTCMonth(),Math.min(today.getUTCDate(),new Date(Date.UTC(lastMonth.getUTCFullYear(),lastMonth.getUTCMonth()+1,0)).getUTCDate())));
 const maxOffset=weeks?(end.getUTCFullYear()-today.getUTCFullYear())*12+end.getUTCMonth()-today.getUTCMonth():months;
 const index=Math.min(offset,maxOffset);
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
  <View style={{borderLeftWidth:4,borderLeftColor:'#69DDB0',paddingLeft:10}}><Heading subtitle="Tippe auf einen Tag für Status und Sitzplatz">Reservierungskalender</Heading></View>
  <Body>Zeitraum: {dateKey(today)} bis {dateKey(end)}</Body>
  <View style={{flexDirection:'row',alignItems:'center',justifyContent:'space-between',marginVertical:12}}>
   <Pressable accessibilityRole="button" accessibilityLabel="Vorheriger Monat" disabled={index===0} onPress={()=>{setOffset(index-1);setSelected(null);}} style={{minWidth:44,minHeight:44,alignItems:'center',justifyContent:'center',opacity:index===0?.35:1}}><Text style={{color:T.text,fontSize:24}}>‹</Text></Pressable>
   <Body style={{fontWeight:'800'}}>{monthLabel(first)}</Body>
   <Pressable accessibilityRole="button" accessibilityLabel="Nächster Monat" disabled={index>=maxOffset} onPress={()=>{setOffset(index+1);setSelected(null);}} style={{minWidth:44,minHeight:44,alignItems:'center',justifyContent:'center',opacity:index>=maxOffset?.35:1}}><Text style={{color:T.text,fontSize:24}}>›</Text></Pressable>
  </View>
  <View style={{flexDirection:'row'}}>{['Mo','Di','Mi','Do','Fr','Sa','So'].map(day=><Text key={day} style={{flex:1,textAlign:'center',color:T.muted,fontSize:12}}>{day}</Text>)}</View>
  {rows.map((row,i)=><View key={i} style={{flexDirection:'row',marginTop:3}}>{row.map((d,j)=>{
   if(!d)return <View key={j} style={{flex:1}}/>;
   const key=dateKey(d),[label,color,bg]=status(d);
   return <Pressable key={j} accessibilityRole="button" accessibilityLabel={key+' '+label} onPress={()=>setSelected({key,label})} style={{flex:1,minHeight:44,marginHorizontal:1,borderRadius:7,backgroundColor:bg,borderWidth:1,borderColor:selected?.key===key?T.accent:T.line,alignItems:'center',justifyContent:'center'}}><Text style={{color,fontWeight:'700'}}>{d.getUTCDate()}</Text><Text style={{color,fontSize:10}}>{label==='Bestätigt'?'✓':(label==='Geprüft, nicht bestätigt'||label==='Bestellung ungeklärt')?'!':label==='Noch nicht bestätigt / unbekannt'?'?':'–'}</Text></Pressable>;
  })}</View>)}
  <View style={{marginTop:12,gap:5}}>
   <Body style={{color:T.green}}>✓ Bestätigte Reservierung</Body>
   <Body style={{color:T.red}}>! Geprüft, nicht bestätigt</Body>
   <Body style={{color:T.orange}}>? Noch nicht bestätigt</Body>
   <Body style={{color:T.orange}}>! Bestellung ungeklärt (gesperrt)</Body>
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
 const [weeks,setWeeks]=useState(null);
 useEffect(()=>{if(host?.weeksAhead){setWeeks(host.weeksAhead);}else if(host?.monthsAhead){setWeeks(null);setMonths(String(host.monthsAhead));}},[host?.weeksAhead,host?.monthsAhead]);
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
  try{const r=await remote.request('/oracle/control',{method:'POST',body:{action,time,...(weeks?{weeks}:{months:Number(months)}),confirm:'WESTBAHN-STEUERUNG'}});setPending(r.id);setNotice('Auftrag angenommen, Ausführung noch nicht bestätigt.');}
  catch(e){setError('Auftrag unklar: '+e.message+' — Serverstatus prüfen, nicht blind wiederholen.');}finally{sending.current=false;setBusy(false);}
 }
 async function checkResult(){
  if(!pending||checking.current)return;
  checking.current=true;
  try{const r=await remote.request('/oracle/control-result?id='+encodeURIComponent(pending));setNotice(r.status==='completed'?(pendingAction.current==='book_now'?'Startauftrag angenommen; Buchungsergebnis folgt im Bericht.':pendingAction.current==='stop_booking'?'Abbruch angefordert. Aktuelle Bestellung wird gegebenenfalls noch abgeglichen.':'Änderung bestätigt'):r.status==='failed'?'Änderung fehlgeschlagen':'Auftrag noch offen');if(r.status!=='pending'){setPending(null);await refresh();}}
  catch(e){setError(e.message);}finally{checking.current=false;}
 }
 useEffect(()=>{if(!pending)return;const timer=setInterval(checkResult,5000);return ()=>clearInterval(timer);},[pending,remote.request]);
 function confirm(action){Alert.alert('Automatik ändern',action==='stop_booking'?'Buchungslauf kontrolliert beenden? Eine bereits begonnene Bestellung wird noch abgeglichen. Bestehende Tickets und Wochenautomatik bleiben unverändert.':action==='book_now'?'Jetzt den bestehenden Buchungsdienst starten? Es gelten der gespeicherte Vorlauf und die bisherige Preisprüfung mit Restrisiko.':action==='horizon'?'Buchungsvorlauf auf '+(weeks?weeks+(weeks===1?' Woche':' Wochen'):months+' Monate')+' setzen?':action==='pause'?'Zukünftige Läufe pausieren. Laufende Buchungen werden nicht abgebrochen.':action==='resume'?'Automatik fortsetzen. Ein verpasster Lauf kann nachgeholt werden.':'Montagszeit ändern auf '+time+' (Europe/Vienna).',[{text:'Abbrechen',style:'cancel'},{text:'Bestätigen',onPress:()=>control(action)}]);}
 const report=data?.report;
 const saved=host?.savedReservations;
 const savedSet=new Set(saved||[]);
 const [tab,setTab]=useState('overview');
 const nowParts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Vienna',year:'numeric',month:'numeric',day:'numeric'}).formatToParts(new Date());
 const getPart=k=>Number(nowParts.find(p=>p.type===k)?.value);
 const start=new Date(Date.UTC(getPart('year'),getPart('month')-1,getPart('day')));
 const horizon=host?.monthsAhead;
 const endMonth=Number.isInteger(horizon)?new Date(Date.UTC(start.getUTCFullYear(),start.getUTCMonth()+horizon,1)):null;
 const end=host?.weeksAhead?new Date(start.getTime()+host.weeksAhead*7*86400000):endMonth?new Date(Date.UTC(endMonth.getUTCFullYear(),endMonth.getUTCMonth(),Math.min(start.getUTCDate(),new Date(Date.UTC(endMonth.getUTCFullYear(),endMonth.getUTCMonth()+1,0)).getUTCDate()))):null;
 const targets=[];
 if(end)for(let d=new Date(start);d<=end;d.setUTCDate(d.getUTCDate()+1)){if(d.getUTCDay()>0&&d.getUTCDay()<6)targets.push(dateKey(d));}
 const pendingDates=host?.pendingReservations;
 const effective=new Set([...(saved||[]),...(host?.progress?.confirmed||[]),...(host?.progress?.newlyBooked||[])]);
 const covered=targets.filter(d=>effective.has(d)&&!pendingDates?.includes(d)).length;
 const percent=targets.length&&Array.isArray(saved)?Math.round(covered/targets.length*100):null;
 const activityLabels={timetable:'Verbindung nicht eindeutig gefunden – Tag übersprungen',pending_order:'Bestellung ungeklärt – keine Wiederholung',cancelled:'Abbruch angefordert',conflict:'Widersprüchliche Buchungsnachweise',bulk:'Gmail-Sammelprüfung läuft',bulk_done:'Gmail-Sammelprüfung abgeschlossen',bulk_unclear:'Gmail-Sammelprüfung unvollständig',cache:'Reservierungsspeicher geladen',inventory:'Prüft WESTbahn-Ticketbestand',checkout:'Bestellvorgang gestartet',reconcile:'Prüft Bestellbestätigung',checking:'Prüft Reisetag',confirmed:'Bereits gebucht',new:'Neue Buchung bestätigt',retry:'Gmail-Abfrage wiederholen',stopped:'Buchung gestoppt – Bestätigung oder Prüfung unklar',skipped:'Prüfung unklar – übersprungen'};
 const stateLabel=s=>({active:'Aktiv',inactive:'Inaktiv',activating:'Läuft / startet',deactivating:'Wird beendet',failed:'Fehler'}[s]||s);
 const canStart=host&&(Number.isInteger(host.monthsAhead)||Number.isInteger(host.weeksAhead))&&['inactive','failed'].includes(host.service.active)&&!busy&&!pending;
 const running=['active','activating'].includes(host?.service?.active);
 const p=host?.progress;
 const fmt=d=>d?new Date(d+'T00:00:00Z').toLocaleDateString('de-AT',{timeZone:'UTC',day:'2-digit',month:'2-digit',year:'numeric'}):'—';
 const latest=Array.isArray(saved)&&saved.length?[...saved].sort().at(-1):null;
 const next=targets.find(d=>!effective.has(d)||pendingDates?.includes(d));
 let contiguous=null;
 if(Array.isArray(saved))for(const d of targets){if(!effective.has(d)||pendingDates?.includes(d))break;contiguous=d;}
 const statusText=!host?'Server nicht erreichbar':pending?'Steuerauftrag offen':running?(activityLabels[p?.phase]||'Buchung läuft'):host.service.active==='failed'?'Letzter Lauf mit Fehler':host.service.active==='deactivating'?'Wird beendet':'Bereit';
 const tabs=[['overview','Übersicht','▦','#64B5FF','#19344F','Buchungsstand und Schnellstart'],['tickets','Tickets','▤','#69DDB0','#193D35','Kalender und Sitzplätze'],['history','Verlauf','◷','#F5C16B','#49391F','Aktivitäten, Berichte und Sicherungen'],['settings','Steuerung','⚙','#C3A6FF','#36294E','Automatik, Vorlauf und Zeitplan']];
 const activeTab=tabs.find(t=>t[0]===tab);
 const sectionColors={overview:'#64B5FF',tickets:'#69DDB0',history:'#F5C16B',settings:'#C3A6FF'};
 return <View style={{flex:1,backgroundColor:T.bg}}>
 <View style={{paddingHorizontal:16,paddingTop:12,paddingBottom:10,gap:10}}>
 <View style={{flexDirection:'row',alignItems:'center',justifyContent:'space-between'}}>
 <View><Text style={{color:T.muted,fontSize:11,fontWeight:'700',letterSpacing:2}}>AGENTZENTRALE</Text><Text style={{color:T.text,fontSize:28,fontWeight:'800'}}>WESTbahn</Text></View>
 <Pressable accessibilityRole="button" accessibilityLabel="Aktualisieren" disabled={busy||!remote.connected} onPress={refresh} style={{borderRadius:14,backgroundColor:T.surface2,minHeight:44,minWidth:44,alignItems:'center',justifyContent:'center'}}><Text style={{color:T.accent,fontSize:23}}>↻</Text></Pressable>
 </View>
 <View style={{flexDirection:'row',backgroundColor:T.surface,borderRadius:14,padding:4,gap:2}}>{tabs.map(([key,label,symbol,color,bg])=><Pressable key={key} accessibilityRole="tab" accessibilityState={{selected:tab===key}} onPress={()=>setTab(key)} style={{flex:1,minHeight:44,borderRadius:10,alignItems:'center',justifyContent:'center',backgroundColor:tab===key?bg:'transparent',borderBottomWidth:tab===key?2:0,borderBottomColor:color,paddingVertical:5}}><Text style={{color,fontSize:21,fontWeight:'700'}}>{symbol}</Text><Text style={{color:tab===key?color:T.text,fontWeight:'700',fontSize:12}}>{label}</Text></Pressable>)}</View>
 <View style={{borderLeftWidth:3,borderLeftColor:activeTab[3],paddingLeft:10,paddingVertical:4}}><Text style={{color:activeTab[3],fontSize:13,fontWeight:'700'}}>{activeTab[5]}</Text></View>
 </View>
 <ScrollView style={{flex:1}} contentContainerStyle={styles.page} refreshControl={<RefreshControl refreshing={busy} onRefresh={refresh}/>}>
 <View style={{flexDirection:'row',alignItems:'center',gap:8,paddingVertical:4}}><View style={{width:9,height:9,borderRadius:5,backgroundColor:!host||pending?T.orange:running?T.green:host.service.active==='failed'?T.red:T.green}}/><Text style={{color:!host||pending?T.orange:host.service.active==='failed'?T.red:T.green,fontSize:13,fontWeight:'700',flex:1}}>{statusText}</Text></View>
 {error?<Card><Body style={{color:T.orange}}>{error}</Body></Card>:null}
 {notice?<Card><Body>{notice}</Body>{pending?<ActionButton title="Auftrag prüfen" secondary disabled={busy} onPress={checkResult}/>:null}</Card>:null}
 {tab==='overview'?<>
 <View style={{backgroundColor:'#142D49',borderRadius:22,padding:18,gap:12,borderWidth:1,borderColor:'#315C87'}}>
 <Text style={{color:'#A5D9CF',fontSize:12,fontWeight:'700',letterSpacing:1}}>DEINE TÄGLICHE VERBINDUNG</Text>
 <View style={{flexDirection:'row',alignItems:'center',justifyContent:'space-between',gap:8}}>
 <View style={{flex:1}}><Text style={{color:'#FFFFFF',fontSize:25,fontWeight:'800'}}>18:22</Text><Text style={{color:'#B7D3D2',fontSize:13}}>Wien Meidling</Text></View>
 <Text style={{color:'#8FE2CC',fontSize:23}}>→</Text>
 <View style={{flex:1,alignItems:'flex-end'}}><Text style={{color:'#FFFFFF',fontSize:18,fontWeight:'800'}}>Wr. Neustadt</Text><Text style={{color:'#B7D3D2',fontSize:13}}>Hauptbahnhof</Text></View>
 </View><Text style={{color:'#A5D9CF',fontSize:12}}>Sollverbindung · Mo–Fr · Comfort Class 2+</Text>
 </View>
 <Card><View style={{borderLeftWidth:4,borderLeftColor:sectionColors.overview,paddingLeft:10}}><Heading subtitle="Wie viele Reisetage sind bereits reserviert?">Buchungsfortschritt</Heading></View>
 <View style={{flexDirection:'row',alignItems:'baseline',gap:8}}><Text style={{color:T.green,fontSize:40,fontWeight:'800'}}>{percent===null?'—':percent+'%'}</Text><Muted>{percent===null?'Daten fehlen':covered+' / '+targets.length+' Reisetage'}</Muted></View>
 {percent!==null?<View style={{height:9,borderRadius:6,backgroundColor:T.surface2,overflow:'hidden'}}><View style={{height:9,width:percent+'%',backgroundColor:T.green}}/></View>:null}
 <View style={{flexDirection:'row',gap:8,marginTop:8}}>{[['Bestätigt',Array.isArray(saved)?String(saved.length):'—','#69DDB0','#193D35'],['Noch offen',percent===null?'—':String(targets.length-covered),'#F5C16B','#49391F']].map(([label,value,color,bg])=><View key={label} style={{flex:1,padding:12,borderRadius:14,backgroundColor:bg}}><Text style={{fontSize:24,fontWeight:'800',color}}>{value}</Text><Text style={{fontSize:12,color}}>{label}</Text></View>)}</View>
 <Body>Lückenlos im aktuellen Ziel: {fmt(contiguous)}</Body><Muted>Letzter gespeicherter Tag: {fmt(latest)} · Ziel bis {end?fmt(dateKey(end)):'—'}</Muted><Muted>Nachweisstand, keine Live-Garantie gegen Stornierungen.</Muted>
 </Card>
 <Card><View style={{borderLeftWidth:4,borderLeftColor:sectionColors.overview,paddingLeft:10}}><Heading subtitle="Reservierungen starten oder laufenden Auftrag beenden">Jetzt buchen</Heading></View><Body>Nächster offener Reisetag: {fmt(next)}</Body>
 {running?<><Body>Aktuell: {fmt(p?.currentDay)}</Body><Muted>Neu bestätigt: {p?.newlyBooked?.length??'—'}</Muted><ActionButton title="Buchungslauf abbrechen" danger disabled={!!pending||busy} onPress={()=>confirm('stop_booking')}/></>:<ActionButton title="Jetzt maximal vorausbuchen" disabled={!canStart} onPress={()=>confirm('book_now')}/>}
 <Muted>Automatik: {host?.timer?.enabled?'Aktiv':host?'Pausiert':'Unbekannt'} · {host?.timer?.next||'Nächster Lauf unbekannt'}</Muted></Card>
 {Array.isArray(pendingDates)&&pendingDates.length?<Card><View style={{borderLeftWidth:4,borderLeftColor:T.orange,paddingLeft:10}}><Heading subtitle="Nicht erneut buchen, bis der Status geklärt ist">Achtung: offene Bestellungen</Heading></View>{pendingDates.map(d=><Body key={d} style={{color:T.orange}}>{fmt(d)} · Gesperrt</Body>)}<Muted>Keine automatische Wiederholung.</Muted></Card>:null}
 {pendingDates==null?<Muted>Bestellsperren vom Server nicht gemeldet.</Muted>:null}
 <ActionButton secondary title="Reservierungskalender öffnen" onPress={()=>setTab('tickets')}/>
 </>:null}
 {tab==='tickets'?<>
 <BookingCalendar pendingDates={pendingDates} reservations={host?.reservations} saved={saved} report={report} horizon={host?.monthsAhead} weeks={host?.weeksAhead} progress={running?p:null}/>
 <Card><Heading subtitle="Nur nachgewiesene Sitzplätze">Meine Reservierungen</Heading>
 {Array.isArray(saved)?[...saved].sort().map(d=>{const r=host?.reservations?.find(x=>x.date===d);return <View key={d} style={{flexDirection:'row',alignItems:'center',gap:12,paddingVertical:12,borderBottomWidth:1,borderColor:T.line}}><View style={{flex:1}}><Body>{fmt(d)}</Body><Muted>{pendingDates?.includes(d)?'Ungeklärt':r?.source==='manual_westbahn_verification'?'Manuell bestätigt':r?.source==='official_email'?'Gmail-Nachweis':r?.source==='official_account'?'WESTbahn-Konto':'Gespeicherter Nachweis'}</Muted></View><View style={{padding:10,borderRadius:12,backgroundColor:'#193D35'}}><Text style={{color:'#69DDB0',fontWeight:'800'}}>{r?.seat||'—'}</Text><Text style={{color:T.muted,fontSize:10}}>Sitzplatz</Text></View></View>}):<Muted>Serverspeicher nicht verfügbar.</Muted>}
 </Card></>:null}
 {tab==='history'?<>
 <Card><View style={{borderLeftWidth:4,borderLeftColor:sectionColors.history,paddingLeft:10}}><Heading subtitle="Was der Agent zuletzt gemacht hat">Live-Aktivität</Heading></View>{p?.events?.length?p.events.slice(-20).reverse().map((e,i)=><View key={i} style={{paddingVertical:10,borderBottomWidth:1,borderColor:T.line}}><Body>{activityLabels[e.phase]||e.phase}</Body><Muted>{e.day?fmt(e.day):'System'}{e.count!=null?' · '+e.count:''}</Muted></View>):<Muted>Keine Aktivitäten gemeldet.</Muted>}</Card>
 <Card><Heading>Letzter Abschlussbericht</Heading>{report?<><Body>{report.gesamt_bestaetigt} bestätigt · {report.neu_gebucht?.length??0} neu</Body><Muted>{report.erstellt} · {report.dienst_status}</Muted>{report.offene_gepruefte_tage?.map(d=><Body key={d}>{fmt(d)} · {savedSet.has(d)?'Später bestätigt':'Offen im Bericht'}</Body>)}</>:<Muted>Kein Bericht verfügbar.</Muted>}</Card>
 <Card><Heading>Frühere Buchungsläufe</Heading>{host?.history?.length?host.history.map((r,i)=><View key={i} style={{paddingVertical:10,borderBottomWidth:1,borderColor:T.line}}><Body>{new Date(r.erstellt).toLocaleString('de-AT')}</Body><Muted>{r.dienst_status} · {r.gesamt_bestaetigt??'—'} bestätigt · {r.offene_gepruefte_tage.length} offen</Muted></View>):<Muted>Keine historischen Berichte verfügbar.</Muted>}<Muted>Letzte Sicherung: {host?.backupAt||'Nicht gemeldet'}</Muted></Card>
 </>:null}
 {tab==='settings'?<>
 <Card><View style={{borderLeftWidth:4,borderLeftColor:sectionColors.settings,paddingLeft:10}}><Heading subtitle="Wann der Agent automatisch reserviert">Wochenautomatik</Heading></View><Body>{host?.timer?.enabled?'Aktiv':host?'Pausiert':'Unbekannt'}</Body><ActionButton title={host?.timer?.enabled?'Automatik pausieren':'Automatik fortsetzen'} secondary disabled={!host||busy||!!pending} onPress={()=>confirm(host.timer.enabled?'pause':'resume')}/>
 <Muted>Montagszeit (Wien)</Muted><TextInput accessibilityLabel="Montagszeit" value={time} onChangeText={setTime} style={styles.input} maxLength={5}/><ActionButton title="Zeitplan ändern" secondary disabled={!host?.timer.enabled||busy||!!pending||!/^([01][0-9]|2[0-3]):[0-5][0-9]$/.test(time)} onPress={()=>confirm('schedule')}/></Card>
 <Card><Heading>Buchungsvorlauf</Heading><Body>Gespeichert: {host?.weeksAhead?host.weeksAhead+(host.weeksAhead===1?' Woche':' Wochen'):(host?.monthsAhead??'—')+' Monate'}</Body><Muted>Wochen</Muted><View style={{flexDirection:'row',gap:5}}>{[1,2,3].map(n=><Pressable key={n} accessibilityRole="button" accessibilityState={{selected:weeks===n}} onPress={()=>setWeeks(n)} style={{flex:1,minHeight:44,borderRadius:10,backgroundColor:weeks===n?T.accent:T.surface2,alignItems:'center',justifyContent:'center'}}><Text style={{fontWeight:'800',color:weeks===n?'#101820':T.text}}>{n} {n===1?'Woche':'Wochen'}</Text></Pressable>)}</View><Muted>Monate</Muted><View style={{flexDirection:'row',gap:5}}>{[1,2,3,4,5,6].map(n=><Pressable key={n} accessibilityRole="button" accessibilityState={{selected:!weeks&&months===String(n)}} onPress={()=>{setWeeks(null);setMonths(String(n));}} style={{flex:1,minHeight:44,borderRadius:10,backgroundColor:!weeks&&months===String(n)?T.accent:T.surface2,alignItems:'center',justifyContent:'center'}}><Text style={{fontWeight:'800',color:!weeks&&months===String(n)?'#101820':T.text}}>{n}</Text></Pressable>)}</View><ActionButton title="Vorlauf speichern" secondary disabled={!host||busy||!!pending} onPress={()=>confirm('horizon')}/></Card>
 <Card><Heading>Server & Sicherheit</Heading><Body>Telegram: {host?.telegramConfigured?'Konfiguriert':'Nicht bestätigt'}</Body><Body>Dienst: {stateLabel(host?.service?.active)||'Unbekannt'}</Body><Muted>Bestehende Preisprüfung und Doppelbuchungsschutz unverändert. Abbruch storniert keine Tickets.</Muted></Card>
 </>:null}
 <Muted>Serverstand: {host?.timestamp?new Date(host.timestamp).toLocaleString('de-AT'):'Nicht verfügbar'} · Aktualisierung alle 20 Sekunden</Muted>
 </ScrollView></View>;
}
