> Öffentlicher Entwicklungsstand: Die WESTbahn-Reisedaten und Sitzplätze sind ausschließlich Beispieldaten. Persönliche Buchungsregeln werden erst in einer privaten Konfiguration eingerichtet.

# AgentZentrale 1.2 – Multifunktions-Agent für Android

**Status:** Aktualisierter React-Native-/Expo-Quellcode mit funktionierendem lokalen Aufgabensystem, zusätzlichem KI-Chat und einem optionalen eigenständigen Server für die OpenAI- und GitHub-APIs. Der Server und alle externen Konten sind **noch nicht eingerichtet oder produktiv verbunden**. Der GitHub-Agent wurde mit simulierten API-Antworten getestet; die echte GitHub-/OpenAI-Integration sowie ein echter Android-Build wurden in dieser Umgebung **nicht** end-to-end getestet. Es liegt **noch keine APK** vor.

## Was funktioniert

| Bereich | V1.2 | Voraussetzungen |
|---|---|---|
| Zentrale, Aufgaben, Notizen, Freigaben, Verlauf | Lokale Funktionen, Datenpersistenz | Android/Expo |
| V1-Daten übernehmen | Automatische Migration von Datenschema 1 nach 2, kein Datenverlust im Migrationstest | Vorhandener V1-App-Speicher |
| KI-Chat | Anfragen über `/chat`, Nachrichtenverlauf lokal | Eigener HTTPS-Server + OpenAI-API-Key |
| GitHub-Repositories | Repos und Ordner durchsuchen, Textdateien auslesen | HTTPS-Server, für private Repos GitHub-Token |
| KI-Codevorschläge | Vollständiger geänderter Dateiinhalt mit Vorschau und Verwerfen | OpenAI-API-Key und Repository-Leserechte |
| GitHub-Entwurfs-PR | Neuer Branch + Entwurfs-PR erst nach **separater Nutzungsfreigabe** | GitHub-Token mit Schreibrechten + Schalter `ENABLE_GITHUB_WRITE=true` |
| Automatischer Merge / E-Mail-Versand | **Nicht enthalten** | — |

Der KI-Chat besitzt keine Schreibwerkzeuge. Textantworten lösen keine Aktionen aus. Bei GitHub-Aufträgen wird die Datei gelesen und an die KI übertragen, aber nur nach deiner Aufforderung. Beim Vorbereiten erfolgt **kein GitHub-Schreibzugriff**. Vorschläge bleiben 10 Minuten im Server-RAM. Der PR-Sender ist standardmäßig deaktiviert.

## Projektstruktur

```text
App.js                           Navigation (5 Tabs + Verlauf/Einstellungen)
src/screens/{Hub,Chat,GitHub,Tasks,Approvals,History,Settings}Screen.js
src/core/engine.js               Offline-Command-Router und Zustand/Migration
src/store/DataContext.js         Lokale Daten über AsyncStorage
src/store/RemoteContext.js       Serververbindung, Token in SecureStore
src/api/client.js                HTTPS-Client mit Fehlerbehandlung
server/index.mjs                 Node HTTP-Backend, OpenAI- und GitHub-Routen
server/lib.mjs                   Eingabevalidierung und Schutzregeln
server/.env.example              Beispielkonfiguration ohne Secrets
tests/ und server/tests/         Automatische Kern- und API-Tests
```

## 1. Android-Test lokal starten

Voraussetzungen: Node.js ab 22.13 und eine zu Expo SDK 57 passende Expo-Go-Version für Android.

```bash
npm install
npx expo install --fix
npm test
npx expo start
```

Bei Android die angezeigte QR-Verbindung mit Expo Go öffnen. Die **Offline-Funktionen** sind ohne eigenen Server nutzbar. Für die beiden Online-Agenten ist zuerst Schritt 2 erforderlich.

## 2. KI-Gateway vorbereiten

Der Server nutzt nur Node.js-Bordmittel und benötigt **keine zusätzlichen npm-Serverpakete**. Auf einem eigenen Computer oder VPS:

```bash
cd server
cp .env.example .env
openssl rand -hex 32  # Ausgabe in AGENTZENTRALE_ACCESS_TOKEN in .env eintragen
# .env bearbeiten: AGENTZENTRALE_ACCESS_TOKEN setzen,
# OPENAI_API_KEY ergänzen, optional GITHUB_TOKEN ergänzen.
node --env-file=.env index.mjs
```

`AGENTZENTRALE_ACCESS_TOKEN` muss mindestens 24 Zeichen lang sein. Gib diesen Schlüssel in der App unter **Einstellungen → Serververbindung** ein. Der OpenAI-Key **darf niemals** in App.js, app.json, SecureStore auf dem Smartphone oder in GitHub-Commits stehen; er gehört ausschließlich in `server/.env`. Verwende die Secret-Verwaltung deines Hosters, wenn vorhanden.

**Wichtig: HTTPS.** Der Server lauscht standardmäßig nur auf `127.0.0.1:8787`. Ein Smartphone kann nicht über dessen eigenes `localhost` auf deinen Computer zugreifen. Richte eine vertrauenswürdige Domain mit TLS-Reverse-Proxy ein. Für einen Server mit Caddy wäre z. B. folgende Konfiguration passend (Domain selbst ersetzen):

```caddyfile
agent.example.at {
    reverse_proxy 127.0.0.1:8787
}
```

Danach ist die Android-App über `https://agent.example.at` erreichbar. Die App akzeptiert ausschließlich HTTPS-URLs. Hosting, DNS, HTTPS und die API-Zugänge sind **nicht** im ZIP automatisch bereitgestellt.

## 3. GitHub-Integration und eingeschränkte Schreibrechte

Öffentliche Repositorys können grundsätzlich ohne GitHub-Token gelesen werden. Für private Repositorys benötigt das Backend einen Fine-grained Personal Access Token oder später eine GitHub App mit **nur den benötigten Repository-Berechtigungen**. Für den Lesezugriff reichen `Contents: Read`; für PRs zusätzlich `Contents: Read/Write` und `Pull requests: Read/Write`. Lege eine **Repository-Allowlist** fest und erlaube nur deine gewünschten GitHub-Konten über `GITHUB_ALLOWED_OWNERS`.

Für das Erzeugen von Entwurfs-Pull-Requests ist zusätzlich notwendig:

```dotenv
GITHUB_ALLOWED_OWNERS=dmpcgold-rgb
ENABLE_GITHUB_WRITE=true
```

Dann: GitHub-Reiter → Konto wählen → Repo und Textdatei wählen → Änderung beschreiben → KI-Vorschau prüfen → in Bestätigungsdialog **Freigeben**. Es entsteht ein neuer Branch `agentzentrale/*` und ein *Draft Pull Request*. **Keine automatische Merge-Aktion, keine Änderung des Hauptbranches.** Aus Sicherheitsgründen können unter anderem `.env`, `google-services.json`, GitHub-Workflow-Dateien und Binärdateien nicht als Änderungsziel ausgewählt werden.

**GitHub-Fehlerfall:** Wird der Branch bereits angelegt, aber die PR-Erstellung schlägt fehl, kann ein nicht mit einem PR verknüpfter Branch zurückbleiben. Diesen bei Bedarf in GitHub prüfen. Ein GitHub-Token auf einem öffentlich erreichbaren Server ist ein Risiko: HTTPS, begrenzte Repository-Rechte, starke Authentifizierung, Systemupdates und spätere Benutzeridentitäten/Rate-Limiting sind erforderlich.

## 4. APK bauen

Das vorhandene `eas.json` enthält das Profil `preview` für ein Android-APK. Nach der Installation und Anmeldung bei Expo:

```bash
npm install
npx expo install --fix
npx eas-cli login
npx eas-cli build --platform android --profile preview
```

Die APK wird erst nach einem tatsächlich erfolgreichen EAS-Build ausgegeben. Dieses Projekt enthält kein vorgebautes APK und keine APK-Downloadadresse. Für Tests mit Expo Go SDK 57 kann eine passende Version erforderlich sein.

## 5. Tests

```bash
npm test
```

Die Tests benötigen für die Backend-API **keinen Internetzugriff** und simulieren Antworten des OpenAI- und GitHub-API. Sie decken unter anderem ab: V1→V2-Datenmigration, Chat-Verlauf, Validierung, Autorisierung, Repo-Lesen, Codevorschläge ohne Schreibzugriff, explizite PR-Freigabe und einmalige Verwendung einer Vorschlags-ID.

## Bewusste Einschränkungen

- Ohne die selbst eingerichtete HTTPS-Verbindung, den OpenAI-API-Key und bei privaten Repositories den GitHub-Zugriff ist nur der **lokale Modus** funktionsfähig.
- Keine Systemhintergrundaufgaben, Push-Erinnerungen, OAuth-Anmeldung, Gmail- oder Kalenderkonto-Verbindung, automatischen Tests fremder Repositories oder vollautomatische Projekt-Releases.
- Chatverlauf und Notizen werden unverschlüsselt über AsyncStorage lokal gespeichert. Nur das **Server-Zugangstoken** wird über Expo SecureStore geschützt. Keine Passwörter oder Geheimnisse in Aufgaben, Notizen oder Chat eingeben.
- Die KI kann Fehler machen. Änderungsvorschläge müssen vor Freigabe geprüft und danach regulär getestet werden.
- Jede KI-Anfrage kann Kosten verursachen. `OPENAI_MODEL` und das tägliche KI-Limit `AI_DAILY_LIMIT` (Standard: 30, serverseitig pro Prozess) sind einstellbar.
- Der Server ist für **einen** Benutzer ausgelegt. Für Mehrbenutzerbetrieb ist eine echte Authentifizierung mit getrennten Berechtigungen erforderlich.

## V1.3 – WESTbahn-Agent

Im Dashboard „WESTbahn-Agent öffnen“: Wochenplan, Sitzplatzregeln, Buchungsstatus und Link zur offiziellen WESTbahn. Die App plant Montag–Freitag um 18:22 von Wien Meidling nach Wiener Neustadt Hbf bis sechs Kalendermonate im Voraus; tatsächliche Fahrten und Sitzplätze müssen der Anbieter bestätigen. Kein Feiertags-/Urlaubsfilter in V1.3. Die App öffnet die offizielle Reservierungsseite auch ohne Server.

**Live-Buchungen sind noch NICHT möglich:** Es wurde keine öffentliche, dokumentierte und verifizierte Buchungs-API gefunden; kein echter WESTbahn-Adapter und keine Anmeldedaten sind enthalten. Es wurden keine Reservierungen vorgenommen. Ein Anbieteradapter muss vom Betreiber über eine zulässige, tatsächlich getestete Schnittstelle eingerichtet werden. Ohne Adapter bleiben Automatik und Checkout gesperrt. Keine Zahlungen > 0 € werden unterstützt. Die Buchungsregeln sind serverseitig fest vorgegeben.

### Anbieteradapter (Vertrag, keine echte Schnittstelle)

Ein lokales ES-Modul mit `export async function createAdapter()` liefert `existing`, `search`, `quote`, `book`. Konfiguration in der Server-.env: `WESTBAHN_ADAPTER_MODULE=/absoluter/pfad/adapter.mjs`, `WESTBAHN_LEDGER=/sicherer/pfad/westbahn.json`. Anbieter-Credentials bleiben ausschließlich serverseitig. Der Adapter muss die tatsächlichen Anbieter-Daten normalisieren:

- `existing({date,...rules})`: `{status:'none'}` nur bei überprüftem Nichtvorhandensein; sonst `{status:'confirmed',receipt,seat}` bzw. `{status:'unknown'}`. Sitzdaten müssen die tatsächliche Anordnung bestätigen.
- `search({date,...rules})`: `{status:'available',date,origin,destination,departure,class,connectionId,seats:[{id,available,class,groupSize:2,layout:'opposite-table'|'offset'}]}` oder `{status:'unavailable'}`. Viererplätze, unklare Layouts und andere Verbindungen werden nicht akzeptiert.
- `quote({date,seat,connectionId,...rules})`: `{date,origin,destination,departure,class,ticket,seat,quoteId,currency:'EUR',totalCents:0}`. Quote muss exakt und aktuell sein.
- `book({quoteId,idempotencyKey,maxTotalCents:0})`: muss das Preislimit **atomar im Anbieter-Checkout** durchsetzen und doppelte Aufträge verhindern; andernfalls nicht verwenden. Bei Erfolg bestätigter Beleg `{confirmed:true,bookingId,date,origin,destination,departure,class,ticket,seat,currency:'EUR',totalCents:0}`. Ohne eindeutigen Beleg wird nicht automatisch erneut gebucht. Adapter muss Zeitüberschreitungen und unklare Ergebnisse korrekt melden. Keine erfundenen Bestätigungen.

Server läuft dauerhaft und nur eine Instanz nutzt das Ledger. Montag ab 07:00 (Europe/Vienna) einmal pro Kalenderdatum, falls explizit aktiviert und Adapter verfügbar; manuelles Starten ebenfalls nach Null-Euro-Freigabe. Der Status zeigt das letzte **einzelne** bestätigte Datum, nicht eine lückenlose Abdeckung. Ist der Server montags vollständig offline, muss man den Lauf manuell nachholen. Ein aktiver Lauf kann durch Abschalten der Automatik nicht rückgängig gemacht werden. Belege müssen bei unklaren Fällen am Anbieter geprüft werden; erneuter Checkout bleibt gesperrt. Tests simulieren den Anbieter, keine Live-Buchung.

## V1.4: Eigener Cloud-Browser
Die Browser-Suche ist unabhängig vom echten Buchungsadapter. Sie öffnet die offizielle WESTbahn-Website in Chromium, unterstützt ein geschütztes dauerhaftes Browserprofil und versucht eine eindeutig erkennbare Verbindungssuche ohne Checkout. Einrichtung: [server/browser/README.md](server/browser/README.md). Live-Buchungen und der Wochenplan bleiben ohne verifizierten Anbieteradapter deaktiviert. Keine Zahlungsdaten in der App.
