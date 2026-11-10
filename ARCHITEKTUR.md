# AgentZentrale 1.2 – Architektur

## Grundprinzip

```text
Android (React Native / Expo)
 ├── Lokale Aufgaben, Notizen, Freigaben, Ereignisse
 │     └── DataContext + engine.js → AsyncStorage (mit V1-Migration)
 ├── KI-Chat (nur Antworttext)
 │     └── RemoteContext (SecureStore Token) → HTTPS → privates Gateway
 └── GitHub-Agent (ausdrückliche Benutzeraktion)
       ├── Repos/Verzeichnisse/Dateien lesen
       ├── KI-Änderungsvorschlag nur für ausgewählte Datei erzeugen
       ├── Vorschau des vollständigen neuen Inhalts
       └── Nutzer bestätigt → neuer Branch + Draft PR
                                      │
                            Node-22-Gateway
                            ├── Bearer-Authentifizierung
                            ├── kurze Input-/Dateigrößen-Grenzen
                            ├── Owner-Allowlist
                            ├── Rate-Limit 45/min pro Instanz und tägliches KI-Kontingent (standardmäßig 30/Tag)
                            ├── nur zugelassene HTTP-Routen
                            ├── OpenAI Responses API (kein Tool-Calling)
                            └── GitHub REST API
```

## Geheimnisse und Autorisierung

- `OPENAI_API_KEY` und `GITHUB_TOKEN` liegen nur als Umgebungsvariablen auf dem Server. Keine Drittanbieter-Credentials in der APK.
- Der Android-Client speichert sein eigenes 32+-Byte-Bearer-Token in Expo SecureStore; HTTPS ist Pflicht.
- GitHub-Lesezugriff ist durch Eigentümer-Whitelist begrenzt, wenn `GITHUB_ALLOWED_OWNERS` gesetzt ist.
- GitHub-Schreibzugriff setzt **zusätzlich** `ENABLE_GITHUB_WRITE=true` und eine definierte Allowlist voraus.
- Der Server hat keinen API-Endpunkt zum Löschen von Repositories, Mergen von PRs, Versenden von E-Mails oder Ausführen von Shell-Befehlen.
- Ein LLM kann nur einen Vorschlag abgeben. Seine Antwort ist nicht eine Berechtigung oder Befehlsquelle.

## Sichere GitHub-PR-Pipeline

1. `POST /github/proposals` → GitHub-Datei lesen, SHA merken, AI-JSON (`title`, `summary`, `content`) parsen, vollständigen Vorschlag an Client zurückgeben. **Kein Schreibzugriff**.
2. Der Server speichert die Vorlage höchstens 10 Minuten im Prozessspeicher.
3. Nutzer betrachtet Original und neues Dokument und bestätigt in einem gesonderten Android-Dialog.
4. `POST /github/create-pr` mit einmaliger Vorschlags-ID und `confirm='FREIGEBEN'`.
5. Backend prüft Schreibschalter, Token, Allowlist, Alter/Zustand des Vorschlags und erneut die aktuelle Datei-SHA.
6. Auf Basis des Standardbranches einen `agentzentrale/*`-Branch anlegen, **nur** die ausgewählte Datei committen, einen Entwurfs-Pull-Request öffnen. Hauptbranch wird nicht geändert.
7. Erfolgsmeldung mit GitHub-URL. Keine automatische Merge-Aktion.

## Datenmodell

- `schema: 2`
- `tasks[]`: id, title, done, createdAt
- `notes[]`: id, content, createdAt
- `approvals[]`: id, agent, type, label, payload, status
- `events[]`: id, at, text
- `chat[]`: id, role (`user`/`assistant`), content, at (max. 40)

`migrateStoredState()` übernimmt V1-Daten (`schema: 1`) und ergänzt nur das Chatfeld. Veraltete V1-Daten werden nicht verworfen.

## Nicht umgesetzte Sicherheitsfunktionen vor produktivem Einsatz

- OAuth/GitHub-App statt dauerhaftem PAT, echte Benutzer- und Rollenverwaltung
- Persistente/idempotente Jobqueue und Erkennung teilweiser PR-Fehler
- Retry mit Jobstatus, Requestprotokoll ohne Promptinhalt, Alarmierung bei Missbrauch
- Ausführliche App-/Gerätetests, Codeprüfung vor PR, CI-Checks, CSP bei Web-Admin
- Datenschutzrichtlinie, Lösch-/Exportfunktion und getrennte vertrauliche Datenhaltung

## V1.3

`src/core/westbahn.js` definiert die feste Reise-Policy, Wiener Zeit, Kalendertage, Sitzplatz-Ranking und exakte 0-Euro-Quote-/Belegvalidierung. `server/westbahn.mjs` implementiert den Adaptervertrag, persistentes Ledger (atomarer Dateiaustausch), Doppelbuchungsschutz, Fail-closed-Verhalten und Montags-Timer. `server/index.mjs` stellt drei authentifizierte Endpunkte bereit. `WestbahnScreen` zeigt Status und manuelle Freigaben. Externer Live-Anbieteradapter nicht enthalten. Keine kostenpflichtige Zahlung, keine Live-Verifikation und kein Emulator-/Gerätetest.

## V1.4: Browser-Infrastruktur
Android → authentifizierter HTTPS-Gateway → fest definierte Browserbefehle (`probe`, `prepare`) → Python Playwright/Chromium → offizieller WESTbahn-Ticketshop. Browserprofil ist lokal auf dem Server und mit exklusiver Sperre gegen parallele Benutzung geschützt. Es existiert kein allgemeiner Remote-Browser und kein Zugriff auf Browser-Cookies über die API. Der Suchablauf prüft eindeutige Eingabefelder und führt nur die Verbindungssuche aus. Der Buchungsadapter bleibt getrennt und deaktiviert, bis der echte Ticketshop-Ablauf einschließlich Preis, Sitzplan und Buchungsbestätigung verifiziert ist.
