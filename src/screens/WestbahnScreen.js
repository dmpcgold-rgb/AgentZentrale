import React,{useState,useEffect} from 'react';
import {Alert,ScrollView,Linking,Text,TextInput,View} from 'react-native';
import {useRemote} from '../store/RemoteContext';
import {RULES,BOOKING_URL,planDates} from '../core/westbahn';
import {ActionButton,Body,Card,Heading,Muted,Section,styles} from '../components/Kit';
import {T} from '../theme';
const labels={confirmed:'Bestätigt',uncertain:'Unklar – prüfen',blocked:'Gesperrt',unavailable:'Nicht verfügbar',booking:'In Bearbeitung',user_reported:'Bereits gebucht (gemeldet)',existing_verified:'Bestehendes Ticket geprüft'};
export default function WestbahnScreen({navigation}){
 const remote=useRemote();const [data,setData]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[browser,setBrowser]=useState(null),[browserMessage,setBrowserMessage]=useState(''),[auditDate,setAuditDate]=useState(()=>planDates()[0]||'2026-11-17'),[auditSeat,setAuditSeat]=useState('191D'),[seatPreview,setSeatPreview]=useState(null),[previewResult,setPreviewResult]=useState(null),[previewDate,setPreviewDate]=useState(()=>planDates()[0]||'2026-11-17'),[auditResult,setAuditResult]=useState(null),[weekAudit,setWeekAudit]=useState(null),[weeklyState,setWeeklyState]=useState(null),[readiness,setReadiness]=useState(null);
 const dates=planDates();
 useEffect(()=>{
   if(!remote.connected)return;
   let cancelled=false;
   Promise.all([
     remote.request('/westbahn/review-status'),
     remote.request('/westbahn/readiness')
   ]).then(([weekly,prepared])=>{
     if(!cancelled){setWeeklyState(weekly);setReadiness(prepared);}
   }).catch(()=>{});
   return ()=>{cancelled=true;};
 },[remote.connected]);
 async function refreshWeeklyStatus(){
   setBusy(true);setError('');
   try{
     const [weekly,prepared,ledger]=await Promise.all([
       remote.request('/westbahn/review-status'),
       remote.request('/westbahn/readiness'),
       remote.request('/westbahn/status')
     ]);
     setWeeklyState(weekly);setReadiness(prepared);setData(ledger);
   }catch(e){setError(e.message);}finally{setBusy(false);}
 }

 async function request(path,body){setBusy(true);setError('');try{const r=await remote.request(path,body===undefined?{}:{method:'POST',body});if(path==='/westbahn/run'){Alert.alert('Lauf gestartet',r.message);setData(await remote.request('/westbahn/status'));}else setData(r);}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function browserRequest(mode){setBusy(true);setError('');try{const result=await remote.request('/westbahn/browser/'+mode,mode==='status'?{}:{method:'POST',body:mode==='prepare'?{date:dates[0]}:{},timeoutMs:75000});if(mode==='status')setBrowser(result);else setBrowserMessage(result.message);}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function auditFiveDays(){
   setBusy(true);setError('');setWeekAudit(null);
   try {
     const result=await remote.request('/westbahn/browser/audit-week',{
        method:'POST',body:{},timeoutMs:235000
     });
     setWeekAudit(result);
     if(result.ledgerProtectedDates?.length){
       const latest=await remote.request('/westbahn/status');
       setData(latest);
     }
     const weekly=await remote.request('/westbahn/review-status');
     setWeeklyState(weekly);
   }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 async function previewTrip(){
   setBusy(true);setError('');setPreviewResult(null);
   try{
     const result=await remote.request('/westbahn/browser/preview-trip',{
       method:'POST',body:{date:previewDate.trim()},timeoutMs:75000
     });
     setPreviewResult(result);
   }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 async function previewSeatMap(){
   setBusy(true);setError('');setSeatPreview(null);
   try {
     const result=await remote.request('/westbahn/browser/seat-preview',{
       method:'POST',body:{date:previewDate.trim()},timeoutMs:75000
     });
     setSeatPreview(result);
   }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 async function auditExistingTicket(){
   setBusy(true);setError('');setAuditResult(null);
   try {
     const result=await remote.request('/westbahn/browser/audit-ticket',{
       method:'POST',body:{date:auditDate.trim(),seat:auditSeat.trim().toUpperCase()},
       timeoutMs:185000
     });
     setAuditResult(result);
     if(result.ledgerProtected===true) {
       const latest=await remote.request('/westbahn/status');
       setData(latest);
     }
   }catch(e){setError(e.message);}finally{setBusy(false);}
 }
 function authorize(mode){Alert.alert('Nur kostenlose Reservierungen','Nur 0,00 € Gesamtpreis, exakte Verbindung und passende Einzelplätze. Keine kostenpflichtigen Buchungen.',[{text:'Abbrechen',style:'cancel'},{text:'Freigeben',onPress:()=>request(mode==='run'?'/westbahn/run':'/westbahn/settings',mode==='run'?{confirm:'NUR-0-EURO'}:{enabled:true,confirm:'NUR-0-EURO'})}]);}
 return <ScrollView style={{flex:1,backgroundColor:T.bg}} contentContainerStyle={styles.page}>
 <Heading subtitle={`Montag bis Freitag · ${RULES.departure} Uhr · ${RULES.class}`}>WESTbahn-Agent</Heading>
 <Card><Body>{RULES.origin} → {RULES.destination}</Body><Muted>KlimaTicket Österreich · 0 € · Keine Viererplätze</Muted><Body style={{marginTop:8}}>233 A / 233 D → 191 D → 182 A → 193 (nur eindeutig passende Plätze)</Body><Muted>Danach Einzelplätze gegenüber mit Tisch, dann leicht versetzt.</Muted></Card>
 <Card><Heading>Automatik</Heading><Body>Montag ab 07:00 · Europe/Vienna</Body><Muted>Planung ab 17.11.2026 (16.11. bereits manuell reserviert), bis sechs Monate voraus. Tatsächliche Verfügbarkeit wird erst beim Anbieter geprüft.</Muted><Muted style={{marginTop:9}}>{!remote.connected?'Server nicht verbunden.':data?.providerConnected?'Buchungsadapter verbunden.':'Kein bestätigter Live-Buchungsadapter verbunden.'}</Muted><Muted>Automatik: {data?.automatic?'Aktiv':'Aus / noch nicht geprüft'}</Muted><View style={{gap:8,marginTop:10}}><ActionButton title="Status aktualisieren" secondary disabled={busy||!remote.connected} onPress={()=>request('/westbahn/status')}/><ActionButton title="Jetzt 0-€-Buchungen prüfen" disabled={busy||!data?.providerConnected||data?.running} onPress={()=>authorize('run')}/><ActionButton title={data?.automatic?'Automatik deaktivieren':'Automatik aktivieren'} secondary disabled={busy||(!data?.providerConnected&&!data?.automatic)} onPress={()=>data?.automatic?request('/westbahn/settings',{enabled:false}):authorize('settings')}/><ActionButton title="Offizielle WESTbahn öffnen" secondary onPress={()=>Linking.openURL(BOOKING_URL).catch(()=>setError('Website konnte nicht geöffnet werden.'))}/>{!remote.connected?<ActionButton title="Server verbinden" secondary onPress={()=>navigation.navigate('Einstellungen')}/>:null}</View>{error?<Body style={{color:T.red,marginTop:8}}>{error}</Body>:null}</Card>
 <Card>
   <Heading>Automatische Montagskontrolle</Heading>
   <Body>{weeklyState?.enabled?'Reine Ticketprüfung ab Montag 07:00 Uhr – bei Serverausfall Nachholprüfung bis Freitag':'Prüfdienst nicht aktiviert oder Serverstatus unbekannt'}</Body>
   <Muted>Letzter Prüfstart: {weeklyState?.lastRun?.startedAt||'Noch keiner'}</Muted>
   <Muted>Ergebnis: {weeklyState?.lastRun?.status||'Noch keine Prüfung'}</Muted>
   <Muted>Letzte erfolgreiche Kalenderwoche: {weeklyState?.lastSuccessWeek||'Noch keine'}</Muted>
   {weeklyState?.nextRetryAt?<Muted>Nächste sichere Wiederholung: {weeklyState.nextRetryAt}</Muted>:null}
   {weeklyState?.lastRun?.coverage?<Muted>Kontoseiten geprüft: {weeklyState.lastRun.coverage.pagesVerified} von {weeklyState.lastRun.coverage.pagesAttempted} gelesenen Seiten. Vollständigkeit nicht nachgewiesen.</Muted>:null}
   <Muted>Bestellte Tickets: keine – dieser Prüfautomat kann ausschließlich vorhandene Reservierungen lesen.</Muted>
   <View style={{marginTop:10}}>
    <ActionButton title="Montagsprüfung-Status aktualisieren" secondary disabled={busy||!remote.connected} onPress={refreshWeeklyStatus}/>
   </View>
   {readiness?<View style={{marginTop:10,gap:4}}>
     <Muted>Wunschplätze: {readiness.preferredSeats?.join(' / ')} · Preisgrenze: 0 €</Muted>
     {(readiness.days||[]).map(d=><Muted key={d.date}>{d.date} · {d.status==='protected_existing'?'Bereits geschützt':d.status==='checkout_needs_review'?'Bestellung ungeklärt':d.status==='possible_existing'?'Mögliche Reservierung':d.status==='reported_existing'?'Bereits gemeldet':'Bestand nicht vollständig geklärt'}</Muted>)}
     <Muted>Automatischer Kauf: noch nicht freigeschaltet – vollständiger Bestandsnachweis und getesteter Bestelladapter fehlen.</Muted>
   </View>:null}
 </Card>
 <Card><Heading>Cloud-Browser</Heading><Muted>Eigener Chromium-Browser auf dem Server. Anmeldung erfolgt einmal am Server. Ticketprüfung nur lesend, keine Käufe oder Änderungen.</Muted><Muted>{browser?.enabled?'Browser aktiviert.':'Browser noch nicht aktiviert oder Status nicht geprüft.'} {browser?.profilePresent?'Profil vorhanden (Login nicht verifiziert).':''}</Muted><View style={{gap:8,marginTop:10}}><ActionButton title="Browser-Status" secondary disabled={busy||!remote.connected} onPress={()=>browserRequest('status')}/><ActionButton title="WESTbahn im Server-Browser öffnen" secondary disabled={busy||!browser?.enabled} onPress={()=>browserRequest('probe')}/><ActionButton title={'Verbindung suchen: '+(dates[0]||'—')} secondary disabled={busy||!browser?.enabled||!dates[0]} onPress={()=>browserRequest('prepare')}/></View>{browserMessage?<Body style={{marginTop:8}}>{browserMessage}</Body>:null}
 <View style={{marginTop:10}}>
  <ActionButton title="Nächste 5 Pendeltage prüfen" secondary disabled={busy||!remote.connected||!browser?.enabled} onPress={auditFiveDays}/>
 </View>
 {weekAudit?<View style={{marginTop:10,gap:4}}>
   <Body>Bestandsprüfung: {weekAudit.status==='inventory_batch_read'?'Sichtbare Karten gelesen':'Konto nicht vollständig lesbar'}</Body>
   {weekAudit.coverage?<Muted>Kontoseiten: {weekAudit.coverage.pagesVerified} erfolgreich, {weekAudit.coverage.pagesFailed} Fehler. Kein vollständiger Bestandsnachweis.</Muted>:null}
   {(weekAudit.days||[]).map(x=><Muted key={x.date}>{x.date} · {x.status==='detail_verified'?'Ticketdetails vollständig geprüft':x.status==='visible_year_verified'?'Bestehende Karte mit Jahresangabe':x.status==='possible_existing'?'Möglicherweise reserviert':'Nicht sicher geklärt'}{x.seats?.length?' · '+x.seats.join(', '):''}{weekAudit.ledgerProtectedDates?.includes(x.date)?' · Doppelbuchungsschutz aktiv':weekAudit.ledgerReviewDates?.includes(x.date)?' · Protokoll-Konflikt, manuell prüfen':''}</Muted>)}
   <Muted>Kontobestand nicht vollständig bestätigt. Auch bei fehlender Karte kein automatischer Kauf.</Muted>
 </View>:null}
 <Muted style={{marginTop:12}}>Öffentliche Verbindung und Comfort-Anzeigepreis unverbindlich prüfen – ohne Buchung</Muted>
 <View style={{flexDirection:'row',gap:8,marginTop:8}}>
   <TextInput accessibilityLabel="Datum der unverbindlichen Verbindungsprüfung"
     style={[styles.input,{flex:1}]} value={previewDate} onChangeText={setPreviewDate}
     placeholder="JJJJ-MM-TT" placeholderTextColor={T.muted} autoCapitalize="none"/>
 </View>
 <View style={{marginTop:8}}>
  <ActionButton title="Verbindung und Comfort-Preis nur prüfen" secondary
    disabled={busy||!remote.connected||!browser?.enabled} onPress={previewTrip}/>
 </View>
 {previewResult?<View style={{marginTop:10,gap:4}}>
   <Body>{previewResult.status==='existing_ledger_entry'?'Für diesen Tag existiert bereits ein Buchungsvermerk':previewResult.status==='public_connection_found'?'Öffentliche Verbindung gefunden':'Verbindung nicht eindeutig bestätigt'}</Body>
   {previewResult.trainNumber?<Muted>WB {previewResult.trainNumber} · {previewResult.departure}–{previewResult.arrival} · Comfort 2+</Muted>:null}
   <Muted>{previewResult.displayedComfortCents===0?'Angezeigter öffentlicher Comfort-Preis: 0,00 € (nicht verbindlich)':typeof previewResult.displayedComfortCents==='number'?'Angezeigter Comfort-Preis: '+(previewResult.displayedComfortCents/100).toFixed(2)+' € (nicht verbindlich)':'Kein eindeutig geprüfter Comfort-Anzeigepreis'}</Muted>
   <Muted>KlimaTicket-Warenkorb, konkreter Sitzplatz und fehlende Reservierung NICHT bestätigt. Keine Buchungsfreigabe.</Muted>
 </View>:null}
 <View style={{marginTop:10,gap:8}}>
  <ActionButton title="Wunschplätze im Offline-Sitzplan ansehen" secondary
    disabled={busy||!remote.connected||!browser?.enabled} onPress={previewSeatMap}/>
  {seatPreview?<View style={{gap:4}}>
    <Body>{seatPreview.status==='offline_seat_map_observed'?'Isolierter Sitzplan untersucht':seatPreview.status==='existing_ledger_entry'?'Für diesen Tag besteht bereits ein Buchungsvermerk':'Sitzplan nicht eindeutig lesbar'}</Body>
    {(seatPreview.preferredSeats||[]).map(s=><Muted key={s.seat}>{s.seat}: {s.observation==='visible_in_offline_copy'?'Im Offline-Sitzplan sichtbar (nicht live geprüft)':s.observation==='disabled_in_offline_copy'?'Offline als deaktiviert dargestellt':'Nicht eindeutig erkennbar'}</Muted>)}
    <Muted>Keine Live-Verfügbarkeit, keine Sitzplatzauswahl und kein KlimaTicket-Endpreis bestätigt. Keine Buchung.</Muted>
  </View>:null}
 </View>
 <Muted style={{marginTop:12}}>Vorhandenes Ticket im WESTbahn-Konto prüfen – ohne Buchung</Muted>
 <View style={{flexDirection:'row',gap:8,marginTop:8}}>
  <TextInput accessibilityLabel="Reisedatum" style={[styles.input,{flex:2}]} value={auditDate}
   onChangeText={setAuditDate} placeholder="JJJJ-MM-TT" placeholderTextColor={T.muted} autoCapitalize="none"/>
  <TextInput accessibilityLabel="Sitzplatz" style={[styles.input,{flex:1}]} value={auditSeat}
   onChangeText={setAuditSeat} placeholder="191D" placeholderTextColor={T.muted}
   autoCapitalize="characters" maxLength={4}/>
 </View>
 <View style={{marginTop:8}}>
  <ActionButton title="Ticket nur lesend prüfen" secondary disabled={busy||!remote.connected||!browser?.enabled} onPress={auditExistingTicket}/>
 </View>
 {auditResult?<View style={{marginTop:10}}>
   <Body>{auditResult.status==='existing_ticket_verified'?'Vorhandene Ticketdetails erkannt':'Noch kein eindeutig geprüfter Ticketbeleg'}</Body>
   <Muted>{auditResult.date} · {auditResult.seat||'—'} · {auditResult.checks?.yearVerified?'Reisedatum bestätigt':'Datum nicht sicher verifiziert'}</Muted>
   <Muted>{auditResult.ledgerProtected?'Im Buchungsprotokoll gegen Doppelbuchung geschützt.':'Keine gesicherte Bestandsfreigabe; Ticketstatus manuell prüfen.'}</Muted>
   <Muted>Keine neue Reservierung. Fehlende Treffer erlauben keinen automatischen Kauf.</Muted>
 </View>:null}
 </Card>
 <Section><Heading subtitle="Geplante Werktage mit vorhandenen Schutzvermerken">Nächste Fahrten</Heading><Card>{dates.slice(0,10).map(d=>{const existing=(data?.rows||[]).find(r=>r.date===d);return <Body key={d}>{d} · {RULES.departure}{existing?' · '+(labels[existing.status]||existing.status):''}</Body>;})}<Muted>Geplante Werktage insgesamt: {dates.length}</Muted></Card></Section>
 <Section><Heading subtitle="Nur Anbieterbestätigungen zählen">Buchungsprotokoll</Heading><Card><Body>Letztes bestätigtes Datum: {data?.confirmedThrough||'Keines'}</Body><Muted>{data?.running?'Lauf aktiv – Status erneut abrufen.':'Keine laufende Buchung.'}</Muted><Muted>„Bereits gebucht (gemeldet)“ verhindert eine erneute automatische Buchung, ist aber keine unabhängig geprüfte Anbieterbestätigung.</Muted></Card>{(data?.rows||[]).map(r=><Card key={r.date}><Body>{r.date} · {labels[r.status]||r.status}{r.seat?' · '+r.seat:''}</Body><Muted>{r.detail}</Muted>{r.bookingId?<Muted>Bestätigung: {r.bookingId}</Muted>:null}</Card>)}</Section>
 </ScrollView>;
}
