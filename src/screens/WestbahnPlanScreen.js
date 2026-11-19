import React,{useEffect,useState} from 'react';
import {ActivityIndicator,Alert,Pressable,ScrollView,Text,TextInput,View} from 'react-native';
import {useRemote} from '../store/RemoteContext';
import {ActionButton,Body,Card,Heading,Muted,styles} from '../components/Kit';
import {T} from '../theme';

const DEFAULT={
 origin:'Wien Meidling',destination:'Wiener Neustadt Hbf',
 departure:'18:22',weekdays:[1,2,3,4,5],horizon:'2w',
 bookingWindowStart:'07:00',bookingWindowEnd:'19:00'
};
const WEEKDAYS=[['Mo',1],['Di',2],['Mi',3],['Do',4],['Fr',5],['Sa',6],['So',7]];
const HORIZONS=[['1 Woche','1w'],['2 Wochen','2w'],['4 Wochen','4w'],['2 Monate','2m'],['6 Monate','6m']];
const TIME=/^(?:[01]\\d|2[0-3]):[0-5]\\d$/;
function Choice({label,active,onPress}){
 return <Pressable
   accessible accessibilityRole="button" accessibilityState={{selected:active}}
   accessibilityLabel={label} onPress={onPress}
   style={{minHeight:48,justifyContent:'center',alignItems:'center',paddingHorizontal:14,
    borderRadius:12,borderWidth:1,borderColor:active?T.accent:T.line,
    backgroundColor:active?T.accent+'22':T.surface,marginRight:8,marginBottom:9}}>
   <Text style={{color:active?T.accent:T.text,fontSize:14,fontWeight:'700'}}>{label}</Text>
 </Pressable>;
}
function Field({label,value,onChange,placeholder,keyboardType='default'}){
 return <View style={{marginBottom:13}}>
  <Text style={{color:T.muted,fontSize:13,fontWeight:'700',marginBottom:7}}>{label}</Text>
  <TextInput accessibilityLabel={label} style={styles.input}
   placeholder={placeholder} placeholderTextColor={T.muted}
   value={value} onChangeText={onChange} autoCorrect={false}
   keyboardType={keyboardType} autoCapitalize="words"/>
 </View>;
}
export default function WestbahnPlanScreen(){
 const remote=useRemote();
 const [plan,setPlan]=useState(DEFAULT),[dates,setDates]=useState([]);
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const update=(key,value)=>setPlan(p=>({...p,[key]:value}));
 useEffect(()=>{
  if(!remote.connected)return;
  let alive=true;
  setBusy(true);
  remote.request('/westbahn/reservation-plan').then(result=>{
   if(!alive)return;
   setPlan(Object.fromEntries(Object.keys(DEFAULT).map(k=>[k,result[k]])));
   setDates(result.plannedDates||[]);
  }).catch(e=>{if(alive)setNotice('Einstellungen konnten nicht geladen werden: '+e.message);})
    .finally(()=>{if(alive)setBusy(false);});
  return ()=>{alive=false;};
 },[remote.connected]);
 const toggleDay=day=>setPlan(p=>({...p,
  weekdays:p.weekdays.includes(day)?p.weekdays.filter(x=>x!==day):[...p.weekdays,day].sort((a,b)=>a-b)}));
 async function save(){
  if(!remote.connected){setNotice('Bitte zuerst den Server verbinden.');return;}
  if(!plan.origin.trim()||!plan.destination.trim()||
     plan.origin.trim().toLocaleLowerCase('de')===plan.destination.trim().toLocaleLowerCase('de')){
   Alert.alert('Bahnhöfe prüfen','Start und Ziel müssen verschieden sein.');return;
  }
  if(!TIME.test(plan.departure)||!TIME.test(plan.bookingWindowStart)||
     !TIME.test(plan.bookingWindowEnd)||plan.bookingWindowStart>=plan.bookingWindowEnd){
   Alert.alert('Uhrzeit prüfen','Bitte HH:MM eingeben. Das Reservierungsfenster muss vorwärts laufen.');return;
  }
  if(!plan.weekdays.length){Alert.alert('Wochentage','Mindestens einen Tag auswählen.');return;}
  setBusy(true);setNotice('');
  try{
   const payload={...plan,origin:plan.origin.trim(),destination:plan.destination.trim()};
   const res=await remote.request('/westbahn/reservation-plan',
     {method:'POST',body:payload});
   setPlan(Object.fromEntries(Object.keys(DEFAULT).map(k=>[k,res[k]])));
   setDates(res.plannedDates||[]);
   setNotice('Einstellungen auf deinem Server gespeichert.');
  }catch(e){setNotice('Speichern fehlgeschlagen: '+e.message);}
  finally{setBusy(false);}
 }
 return <ScrollView style={{flex:1,backgroundColor:T.bg}}
  keyboardShouldPersistTaps="handled" contentContainerStyle={styles.page}>
  <Heading subtitle="Persönliche Vorgaben für die WESTbahn-Reservierungen">Reservierungsplan</Heading>
  <Card>
   <Heading>Strecke</Heading>
   <Field label="Startbahnhof" value={plan.origin}
     onChange={v=>update('origin',v)} placeholder="Wien Meidling"/>
   <Field label="Zielbahnhof" value={plan.destination}
     onChange={v=>update('destination',v)} placeholder="Wiener Neustadt Hbf"/>
   <Field label="Gewünschte Abfahrtszeit (HH:MM)" value={plan.departure}
     onChange={v=>update('departure',v)} placeholder="18:22" keyboardType="numbers-and-punctuation"/>
   <Muted>Bahnhöfe werden als Text gespeichert. Die Verfügbarkeit und der passende Zug müssen später beim Anbieter verifiziert werden.</Muted>
  </Card>
  <Card>
   <Heading>Wochentage</Heading>
   <Muted style={{marginBottom:12}}>Tippe auf alle Tage, an denen eine Reservierung geplant werden soll.</Muted>
   <View style={{flexDirection:'row',flexWrap:'wrap'}}>
    {WEEKDAYS.map(([label,day])=><Choice key={day} label={label}
      active={plan.weekdays.includes(day)} onPress={()=>toggleDay(day)}/>)}
   </View>
  </Card>
  <Card>
   <Heading>Wann soll der Agent reservieren?</Heading>
   <Muted style={{marginBottom:9}}>Tägliches Zeitfenster (Wiener Zeit)</Muted>
   <View style={{flexDirection:'row',gap:12}}>
    <View style={{flex:1}}><Field label="Von (HH:MM)" value={plan.bookingWindowStart}
      onChange={v=>update('bookingWindowStart',v)} placeholder="07:00" keyboardType="numbers-and-punctuation"/></View>
    <View style={{flex:1}}><Field label="Bis (HH:MM)" value={plan.bookingWindowEnd}
      onChange={v=>update('bookingWindowEnd',v)} placeholder="19:00" keyboardType="numbers-and-punctuation"/></View>
   </View>
   <Muted>Dieses Fenster definiert deine gewünschte Ausführungszeit, nicht die Zugabfahrtszeit.</Muted>
  </Card>
  <Card>
   <Heading>Wie weit im Voraus?</Heading>
   <View style={{flexDirection:'row',flexWrap:'wrap',marginTop:9}}>
    {HORIZONS.map(([label,value])=><Choice key={value} label={label}
      active={plan.horizon===value} onPress={()=>update('horizon',value)}/>)}
   </View>
   <Muted>Maximal sechs Kalendermonate. Eine Reservierung kann nur stattfinden, wenn WESTbahn sie für den jeweiligen Tag bereits anbietet.</Muted>
  </Card>
  <Card>
   <Heading>Vorschau</Heading>
   {dates.length?<Body>Nächste gespeicherte Reisetage: {dates.slice(0,8).join(' · ')}</Body>
     :<Muted>Nach dem Speichern erscheint hier deine Reisetagevorschau.</Muted>}
   <Muted style={{marginTop:9}}>0,00 € bleibt die feste Preisobergrenze. Bevor neue Strecken, Abfahrtszeiten oder größere Zeiträume automatisch gebucht werden, muss der Anbieteradapter dafür verifiziert sein. Das Speichern startet keine Bestellung.</Muted>
  </Card>
  {busy?<ActivityIndicator color={T.accent} style={{marginVertical:12}}/>:null}
  {notice?<Body style={{color:notice.startsWith('Einstellungen')?T.accent:T.orange,marginBottom:12}}>{notice}</Body>:null}
  <ActionButton title="Reservierungsplan speichern" onPress={save}
    disabled={busy||!remote.connected} icon="save-outline"/>
  {!remote.connected?<Muted style={{marginTop:10}}>Der Server ist nicht verbunden. Einstellungen können noch nicht gespeichert werden.</Muted>:null}
 </ScrollView>;
}
