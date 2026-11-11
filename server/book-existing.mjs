// Register a reservation that the user has already obtained from WESTbahn.
// Sends no payment, creates no reservation and never prints credentials.
const [travelDate, seat, ack] = process.argv.slice(2);
if (!/^\\d{4}-\\d{2}-\\d{2}$/.test(travelDate || '') || !/^\\d{3}[A-D]$/.test(seat || '') || ack !== '--confirm-existing') {
 console.error('Aufruf: node book-existing.mjs YYYY-MM-DD 191D --confirm-existing');
 process.exitCode=2;
} else {
 const token=process.env.AGENTZENTRALE_ACCESS_TOKEN;
 const port=Number(process.env.PORT||8787);
 if (!token || token.length<24 || !Number.isInteger(port) || port<1 || port>65535) {
  console.error('Serverkonfiguration fehlt oder ist ungültig.'); process.exitCode=2;
 } else {
  try {
   const response=await fetch('http://127.0.0.1:'+port+'/westbahn/known-booking',{
    method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:JSON.stringify({date:travelDate,seat,confirm:'BESTEHENDE-BUCHUNG'}),
    signal:AbortSignal.timeout(10000)
   });
   if(!response.ok){console.error('Eintrag wurde nicht gespeichert (HTTP '+response.status+').'); process.exitCode=1;}
   else {const result=await response.json();const row=result.rows?.find(r=>r.date===travelDate);
    if(row?.status==='user_reported' && row?.seat===seat) console.log('Buchung geschützt: '+travelDate+' / '+seat+' (vom Nutzer angegeben; keine zusätzliche Buchung).');
    else {console.error('Serverantwort unklar, Eintrag prüfen.');process.exitCode=1;}
   }
  } catch {console.error('AgentZentrale auf localhost nicht erreichbar. Kein Eintrag erstellt.');process.exitCode=1;}
 }
}
