# WESTbahn-Browser V1.4
Der Server startet einen eigenen Chromium-Browser mit Python Playwright. Er ist kein Zugriff auf den ChatGPT Cloud Browser. Es gibt bewusst keine Checkout-Automation, weil die angemeldete WESTbahn-Oberfläche nicht verifiziert wurde.

## Installation (Linux-Server)
Im `server`-Ordner: `python3 -m venv .venv`, `.venv/bin/pip install -r browser/requirements.txt`, `.venv/bin/python -m playwright install chromium` (ggf. mit `--with-deps`). Setze in `.env` `WESTBAHN_PYTHON` auf den absoluten Pfad zur venv-Python-Datei, `WESTBAHN_BROWSER_ENABLED=true` und einen privaten Profilordner. Für die Anmeldung am eigenen Server mit privatem Desktop (z.B. über SSH-geschützte Desktop-Verbindung) dieselben Umgebungsvariablen setzen und `python browser/worker.py login` starten. Einmal im geöffneten WESTbahn-Browser anmelden, dann Enter im Terminal. Nicht parallel mit dem Server-Browser benutzen. Keine Passwörter über die AgentZentrale übermitteln. Profil enthält vertrauliche Sitzungscookies: nur eigener Server, verschlüsselte Festplatte empfohlen, niemals veröffentlichen oder sichern in Git. Zum Abmelden die Browser-Sitzung im Anbieter beenden und das Profil nach Stoppen aller Prozesse entfernen.

Server mit `npm start` starten, HTTPS-Proxy und bestehende AgentZentrale-Authentifizierung beibehalten. In der App WESTbahn → Cloud-Browser → Status → öffnen bzw. Verbindung suchen. Der Test öffnet die offizielle Website. Die Suchfunktion verwendet ausschließlich eindeutige zugängliche Formularfelder, exakt bestätigte Bahnhofsvorschläge, ein natives Datumsfeld und den Button 'Verbindung suchen'. Bei Abweichungen (Cookie-Banner, Login, andere Formularstruktur) stoppt sie. Kein Fahrpreis, Sitzplatz oder Kauf wird angenommen. Das Resultat `search_submitted` bedeutet nur eine ausgelöste Suche, nicht eine verfügbare Verbindung. Der Browser schließt sich danach.

## Freigabe für Live-Buchungen
Vor Live-Buchungen muss der tatsächliche angemeldete Ticketshop in einem privaten Testbrowser analysiert werden: Buchungsbestand prüfen, exakte Verbindung/2+/KlimaTicket erkennen, Sitzplan und Sitzplatzgruppe verifizieren, Gesamtpreis auslesen, Bestätigung eindeutig erkennen, Abbruchfälle testen. Erst dann einen verifizierten Adapter für die vier Methoden `existing`, `search`, `quote`, `book` der V1.3-Schnittstelle ergänzen. Ein unbekannter Checkout darf nie automatisch geklickt werden. Die vorhandene Wochenautomatik bleibt ohne diesen Adapter deaktiviert.

## Private Anmeldung vom Android-Handy (Docker)
Der grafische Login läuft nur bei Bedarf. Auf dem Handy per SSH den lokalen Port 6080 zum Server-Port 6080 weiterleiten (`ssh -L 127.0.0.1:6080:127.0.0.1:6080 ...`). Auf dem Server im Projektverzeichnis `docker compose exec agentzentrale bash /app/server/browser/login-private.sh` ausführen. Im Handy-Browser `http://127.0.0.1:6080/vnc.html` öffnen, das einmalige VNC-Passwort aus dem Terminal eingeben, auf WESTbahn anmelden und anschließend im SSH-Terminal Enter drücken. Die Sitzung und ihre Hilfsprozesse werden beendet; das Chromium-Profil verbleibt im privaten Datenvolume. Niemals Port 6080 im Internet freigeben. Der Login ist erst nach einer tatsächlichen Konto-Prüfung verifiziert; diese Funktion bucht nichts.

## Kontoabfrage (nur lesen)
`docker compose exec -T agentzentrale /opt/agent-venv/bin/python /app/server/browser/worker.py account` prüft die gespeicherte Anmeldung auf der deutschen WESTbahn-Domain und meldet sichtbare passende Comfort-Karten ohne Ticketcodes. Nur die erste sichtbare Seite; kein vollständiger Buchungsbestand. Fehlende Treffer sind kein Nachweis einer fehlenden Reservierung. Buchungsadapter bleibt deaktiviert.

## Domainübergreifender Bestand
Der reguläre Befehl `docker compose exec -T agentzentrale /opt/agent-venv/bin/python /app/server/browser/worker.py account` prüft jetzt die österreichische und deutsche Domain. Standardmäßig werden Seite 1 und 2 sowie weitere sichtbare numerische Seitenlinks (maximal zehn Seiten je Domain) geprüft. `--page 1` prüft nur diese Seite auf beiden Domains. Gleiche sichtbare Datum/Sitzplatz-Kombinationen werden gruppiert, die Quellen bleiben sichtbar. Jahrlose Datumsangaben und unvollständige Seiten sind kein Nachweis eines vollständigen Bestands. Ein Fehler auf einer Domain verwirft positive Treffer auf der anderen nicht. Kein Checkout, keine Buchung.

## Isolierte Sitzplatzvorschau
`worker.py seat-preview --date 2026-11-17` kopiert das geschlossene Browserprofil unter dem Profillock in einen privaten temporären Profilordner (einschließlich IndexedDB und lokaler Einstellungen; ohne Caches, Sperrdateien und Wiederherstellung alter Tabs). Nach der regulären Suche und Prüfung des 0-EUR-Comfort-Buttons werden sämtliche Netzwerkverbindungen des Vorschaukontexts gesperrt, bevor der einzige Comfort-Klick erfolgt. Service Worker und WebSockets sind deaktiviert. Die Vorschau kann nur bereits lokal geladene Platzinformationen anzeigen; ein leeres Ergebnis oder blockierte Anfrage bedeutet nicht, dass der Zug ausgebucht ist. Keine Live-Verfügbarkeit, kein Checkout, keine Buchung.

Die Vorschau ermittelt den Comfort-Preis im temporären Profil erneut. Bei fehlendem oder abweichendem Preis gibt sie die erkannten öffentlichen Preis- und Bedienelementdetails aus und klickt nicht. Das Originalprofil bleibt unverändert; die Kopie wird beim Schließen entfernt.

## Preisvergleich
`worker.py price-audit --date 2026-11-17` vergleicht den Preis im normalen Profil, einer temporären Kopie mit gleichen Browseroptionen und einer Kopie mit den Sicherheitsbeschränkungen der Offline-Vorschau. Pro Ansicht werden vier Preisbeobachtungen und der Anmeldestatus des österreichischen Kontos ermittelt. Keine privaten Kontodaten im Ergebnis, keine Comfort-/Sitzplatzklicks, keine Buchung. Eine Abweichung identifiziert die betroffene Konfiguration, nicht automatisch die genaue Ursache.

Die Offline-Sitzplatzvorschau gibt unter `blockedRequests` zusätzlich Methode, Provider-Domain, Ressourcentyp und eine datensparsam redigierte Pfadstruktur jeder blockierten Anfrage aus. Keine Query-Werte, Header, Cookies, IDs oder Request-Bodies werden ausgegeben. Diese Diagnose erteilt noch keine Online-Freigabe: Auch GET-Anfragen können zustandsändernd sein.

## Preisunabhängige Offline-Netzwerkdiagnose
`worker.py seat-network-diagnostic --date 2026-11-17` nutzt dieselbe temporäre, vor dem Comfort-Klick vollständig offline geschaltete Browserkopie wie `seat-preview`. Nur dieser explizite Diagnosemodus erlaubt die Untersuchung eines eindeutig aktiven Comfort-Buttons auch bei 7,90 EUR oder unbekanntem Preis. Alle Anfragen nach dem Klick werden weiterhin blockiert; keine Sitzplatzauswahl, keine Live-Verfügbarkeit und keine Buchung. `bookingAuthorized` bleibt stets false. Der normale `seat-preview`-Modus behält seine Nullpreisprüfung. Ein Diagnoseergebnis darf niemals als Kaufpreis oder Buchungsfreigabe verwendet werden.

## Manuelle Online-Sitzplanprüfung
`docker compose exec agentzentrale bash /app/server/browser/login-private.sh seat-review --date 2026-11-17` öffnet den privaten grafischen Browser mit dem gespeicherten Profil und bereitet die gewünschte Verbindung vor. Die Suche führt keine Comfort-, Sitzplatz- oder Kaufklicks aus. Der Benutzer kann die offizielle Oberfläche im privaten SSH-Tunnel ansehen. Nur bei sichtbaren 0 EUR manuell zur Sitzübersicht weitergehen, keinen Kauf auslösen. Der bereits diagnostizierte POST `/api/v1/basket/add` ist eine Warenkorbänderung, keine verifizierte Buchung; er wird nicht automatisch freigegeben oder ausgeführt. Eine manuelle Aktion ist nicht automatisch gegen einen Kauf gesperrt. Der Live-Buchungsadapter bleibt deaktiviert.

## Anmeldung vor der Suche
Die regulären Modi `prepare` und `comfort-inspect` öffnen zuerst das österreichische Konto und prüfen sichtbare authentifizierte Kontomerkmale. Bei nicht bestätigtem Konto wird die Suche abgebrochen, nicht gebucht. `seat-review` hält bei fehlender Anmeldung oder einem von 0 EUR abweichenden Preis den privaten Desktop offen: Anmeldung/KlimaTicket im selben Browser prüfen und Enter zum erneuten Versuch; q beendet. Kein Kopieren der Sitzung zwischen Anmeldung und Suche. Der Login-Modus bestätigt das österreichische Konto beim Speichern. Das Docker-Volume `agent-data` bleibt erhalten; Server-seitiger Ablauf von Sitzungen kann nicht verhindert werden. Diagnosen bleiben separat; keine automatische Buchung und kein automatischer Warenkorb-Klick.

## Automatische Wiederanmeldung
`worker.py credentials-set` (interaktiv über SSH mit TTY) erfragt E-Mail und Passwort ohne Passwort-Echo. Die Datei `westbahn-login.json` liegt außerhalb des Chromium-Profils im privaten Docker-Volume, Berechtigungen 0600; sie ist **nicht zusätzlich verschlüsselt**. Administratoren mit Serverzugriff können sie lesen. `credentials-remove` entfernt sie. `login-check` prüft die Sitzung und versucht bei Bedarf eine einmalige Wiederanmeldung über das eindeutige offizielle Loginformular. Konto und Suchseite werden im selben Browser überprüft. Unbekannte Formulare, zusätzliche Sicherheitsprüfungen, Fehler und unbestätigte Anmeldung führen zum Abbruch, ein fehlgeschlagener Anmeldeversuch wird zehn Minuten nicht wiederholt. Keine Buchung; die endgültige KlimaTicket-Preisprüfung und Live-Checkout bleiben separat. Zugangsdaten nicht in Befehlsargumente, Chat, Screenshots oder GitHub schreiben.

## Wunschplätze im geöffneten Sitzplan
Wagen 11, Reihe 233, Plätze 233A und 233D sind anhand der sichtbaren WESTbahn-Oberfläche als bevorzugte Plätze erfasst. In `seat-review` zuerst die Detailseite und den Dialog über „Ändern“ öffnen; anschließend `a` + Enter im SSH-Terminal. Der Agent prüft die eindeutige Dialogstruktur und eine vorhandene Auswahl. Er klickt einen Wunschplatz nur bei eindeutig erkennbarem freien Status, bestätigt niemals die Auswahl und klickt weder Warenkorb noch Kaufen. Bei unbekannter DOM-Struktur oder nicht bestätigtem Platz wird abgebrochen. Kein automatischer Ersatzplatz: Layout und Viererplatz-Ausschluss sind noch nicht verifiziert.

In der manuellen Sitzplanprüfung beendet ausschließlich `q` + Enter den Eingabedialog (oder eine unterbrochene Terminalverbindung). Leeres Enter und unbekannte Eingaben lassen die Sitzung offen. `a` + Enter prüft den geöffneten Sitzplan. Der Startdialog unterscheidet jetzt zwischen Login und Sitzplanprüfung.

Die Sitzplanprüfung verarbeitet Browserereignisse auch während der SSH-Eingabe. Sie ermittelt die tatsächlich geöffnete Detailseite über die aktuelle Dokument-URL und sucht im Browserkontext einen eindeutigen Sitzplandialog für das angeforderte Datum und die Strecke. Mehrere oder fehlende Treffer führen zum Abbruch mit datensparsamer Seitendiagnose. Keine automatische Bestätigung oder Buchung.

## Ersatzplatzstrategie
Im geöffneten Sitzplan prüft `a` zuerst 233A/233D in Wagen 11, dann die vom Benutzer bevorzugten 191D (Wagen 8) und 182A (Wagen 7). Für sonstige Plätze werden sichtbare Wagen untersucht; nur eindeutig identifizierte Comfort-Wagen und explizit als zwei gegenüberliegende Einzelplätze (mit Tisch, danach versetzt) ausgewiesene Sitzgruppen sind zulässig. Vierergruppen bleiben auch bei teilweise belegten Plätzen ausgeschlossen. Die generische Layout-Erkennung benötigt explizite DOM-Gruppen-/Layout-Metadaten; wenn die Live-Seite diese nicht liefert, wird kein unbekannter Ersatzplatz geraten. Wagenidentität wird über aktive Zustandsmerkmale bzw. eindeutige blaue Hervorhebung geprüft. Keine Bestätigung, kein Warenkorb, kein Kauf; Bestandsprüfung und Checkout bleiben separat.

Die Live-Diagnose zeigte `comfortMap:false` und aktivierbare Sitzplatzbuttons ohne Frei-Text. Der Parser prüft jetzt SVG-/Text-/ARIA-Klassenlabels. Nur für 233A/233D, 191D und 182A kann die eindeutige 0-EUR-Comfort-Zusammenfassung des WB 1009 die fehlende Kartenkennzeichnung ergänzen; ein eindeutig aktiver, nicht gesperrter Sitzbutton darf dann zur Auswahl versucht werden. Die tatsächliche Auswahl muss anschließend im Dialog bestätigt erkannt werden. Das ist keine Buchung. Bei generischen Alternativen bleiben explizite Zweiergruppen- und Layoutnachweise zwingend. Die tatsächliche WESTbahn-Struktur wurde noch nicht erneut live getestet.

## Sitzplatzbestätigung (noch ohne Warenkorb)
Im privaten `seat-review` mit offenem Sitzplan prüft `b` + Enter die eindeutige Karte „Meine Auswahl“ (ein Comfort-Produkt, WB 1009, Strecke, Datum, 18:22–18:49, ausschließlich Nullpreise). Nur ein bereits ausdrücklich zugelassener Sitzplatz kann im Dialog bestätigt werden. Anschließend muss die aktualisierte Zusammenfassung exakt den ausgewählten Platz zeigen. Keine automatische Warenkorbänderung und kein Kauf. Der echte Warenkorb muss noch separat untersucht werden; die vollständige Bestands-/Doppelbuchungsprüfung bleibt Voraussetzung für Checkout.

## Sitzplan automatisch öffnen
`a` in `seat-review` öffnet bei Bedarf den aktuell eindeutig mit 0 EUR angezeigten Comfort-Button der erwarteten Verbindung WB 1009 und anschließend den eindeutig zugeordneten „Ändern“-Button der Sitzplatzreservierung. Vor jedem Übergang werden Datum, Strecke bzw. Detailzusammenfassung geprüft. Der erste Comfort-Klick kann beim Anbieter einen vorläufigen Warenkorb-/Auswahlzustand erzeugen; kein Klick auf „In den Warenkorb“, kein Checkout und kein Kauf. Bei Fehlern kein automatischer Wiederholungsklick. `b` bestätigt weiterhin separat nur den Sitzplatz im geöffneten Dialog. Live-Test steht aus.

Die Detailprüfung akzeptiert zusätzlich aufgeteilte Textknoten und Link-/Button-Varianten von „In den Warenkorb“, bleibt aber auf genau eine Auswahlkarte beschränkt. Jede erkannte Nichtnull-Preisangabe innerhalb dieser Karte blockiert die Freigabe; Datum, Strecke, Zug, Uhrzeit, Menge und Sitzplatz müssen weiterhin zusammenpassen. Bei Fehlern werden ausschließlich strukturierte Prüfmerkmale (keine Kontodaten und kein Rohseiteninhalt) ausgegeben. Kein automatischer Kauf.

Die Live-Diagnose vom 17.11.-Test erkannte in der kleinsten Auswahlregion nur einen Nullpreis, ohne Produktdaten. Die Prüfung untersucht jetzt auch begrenzte übergeordnete Container, um eine separate Produktzeile zu erfassen. Sie akzeptiert ausschließlich einen vollständigen zusammenhängenden Bereich und stoppt vor der separaten Sitzplatz-/Preisauswahl, bei Nichtnullpreisen oder zu breitem Seiteninhalt. Strukturierte Diagnosen zeigen die geprüften Ebenen. Keine Buchung.

## Sichere Sitzplanöffnung ohne Checkout
Wenn die Produktkarte nicht eindeutig lesbar ist, darf `a` die Sitzplatzübersicht anhand einer gesonderten schreibgeschützten Vorprüfung öffnen: Detailseite für das exakte Datum und die Strecke, eindeutige `Meine Auswahl`-Fußzeile mit ausschließlich 0 EUR, WB 1009, 18:22–18:49 und Sitzplatzabschnitt. Das davon getrennte 7,90-EUR-Angebot ist kein Gesamtpreis. Diese Vorprüfung **berechtigt weder zur Sitzplatzbestätigung noch zum Warenkorb oder Kauf**; `b` und spätere Checkout-Schritte bleiben strenger und blockieren bei unklaren Produktdaten. Kein unbestätigter Kauf.

## Sitzplatzbearbeitung im Detailbildschirm
Die Erkennung der „Ändern“-Schaltfläche erfasst jetzt auch `a` ohne `href`, Text-Spans mit Framework-Handler und Buttons. Es wird nur ein einziges, kompaktes gemeinsames Überschriftsfeld „Sitzplatzreservierung / Ändern“ akzeptiert. Andere „Ändern“-Links auf derselben Seite, Warenkorb und Kaufaktionen werden nicht angeklickt. Bei Mehrdeutigkeit liefert der Agent eine kleine Diagnose mit Anzahlen und Elementtypen, keine sensiblen Seitendaten.

### Zweiter Einstieg in den Sitzplan bei fehlendem „Ändern“
Die Live-Seitendiagnose vom 11. November ergab genau eine Überschrift „Sitzplatzreservierung“ aber **keinen** sichtbaren Textknoten „Ändern“ (`changeLabelCount=0`). Deshalb gibt es einen gezielten Fallback: Nur wenn „Ändern“ vollständig fehlt, öffnet der Agent den eindeutigen klickbaren **bereits angezeigten Sitzplatzcode** (z. B. `208A`) unter „Wagen / Platz“ innerhalb desselben kompakten Reservierungsabschnitts. Mehrere Sitzplatzlinks, nicht klickbare Texte, fremde Domains oder unklare Abschnitte blockieren den Klick. Er öffnet damit höchstens den Sitzplandialog; keine Bestätigung oder Warenkorbaktion. Die nächste Live-Prüfung wird mit `seatLinkCandidates` und `selectedMode` diagnostiziert.

## Verbesserte Erkennung für die Sitzplan-Öffnung
Die Live-Diagnose ergab `seatHeadingCount=1`, `changeLabelCount=0`, `seatLinkCandidates=0`. Die DOM-Suche berücksichtigt deshalb jetzt unabhängig voneinander sichtbaren Text, ARIA-Beschriftung und Titel. Sie akzeptiert auch „Sitzplatz ändern“, „Platz bearbeiten“ sowie eindeutig klickbare Sitznummern (z. B. als `span` mit Pointer-Cursor), aber ausschließlich in der zugehörigen begrenzten Sitzplatzsektion. Erweiterte Diagnosen zählen die tatsächlich gesehenen Beschriftungen, Sitzcodes und Bedienelemente; es werden keine Zahlungs- oder Buchungsaktionen ausgelöst. Der Live-Test steht noch aus.

## Fehlersuche ohne Preis-/Buchungsrisiko
Unerwartete Playwright-/JavaScript-Fehler während `a` und `b` werden nicht mehr zu einer allgemeinen Meldung zusammengefasst. Das JSON enthält unter `failure` die Phase (`open_comfort_and_seat_map`, `select_preferred_seat` usw.), eine sichere Fehlerkategorie, die Python-Exceptionklasse und Programmstelle im Worker. Die Ausgabe enthält bewusst weder den rohen Fehlertext noch URLs, Tokens, Cookies, Namen, Passwörter oder Seiten-HTML. Es werden dadurch keine zusätzlichen Klicks, Bestätigungen oder Käufe durchgeführt.

## Korrigierter JavaScript-Syntaxfehler
Der GitHub-Browser-Test zeigte `Page.evaluate: SyntaxError: Unexpected token ')'` im Editor-Suchskript. Eine überzählige schließende Klammer in der `leafSeats`-Filterbedingung wurde entfernt. Ein neuer automatisierter Node.js-Syntaxcheck prüft das eingebettete Playwright-JavaScript vor dem Einsatz am Server. Die Sitzplatz- und Kauf-Sicherheitsregeln bleiben unverändert.

### Korrektur: Raster-Spalten bei „Ändern“
Die echte DOM-Diagnose zeigte 1 Sitzplatzüberschrift und 3 Beschriftungstreffer für „Ändern“, aber 0 zugeordnete Controls. Daher entfernt die Erkennung jetzt doppelte verschachtelte Texttreffer und berücksichtigt die tatsächliche Position innerhalb derselben Bildschirmzeile. Das frühere starre Limit für die Höhe bzw. Textlänge des gemeinsamen Containers wurde durch begrenzte Container- und Positionsprüfungen ersetzt. Weiterhin darf niemals ein allgemeines „Ändern“ außerhalb des Sitzplatzbereichs gewählt werden. Zusätzliche Tests decken getrennte Rasterspalten und andere „Ändern“-Knöpfe ab.

### Strukturprüfung für versetztes „Ändern“ (11. November)
Die Live-Diagnose ergab `seatHeadingCount=1`, `changeLabelCount=3`, `editorLabelCandidates=1` und `nearbyEditLabels=0`. Der Agent prüft deshalb zusätzlich, ob Überschrift und genau eine Editor-Schaltfläche in einem **begrenzten gemeinsamen Sitzplatzbereich** liegen, der „Wagen“, „Platz“ und eine Sitznummer enthält, jedoch keinen Warenkorb- oder Checkout-Bereich. Ein bloß gleichlautender Seiten-Button ist nicht ausreichend. Die Diagnose liefert nun bis zu acht Position-/Bereichsnachweise unter `editorEvidence`, ohne Seiteninhalte oder Zugangsdaten. Bei unklarer Zuordnung wird weiter gestoppt.


## Checkout-Prüfung ohne Kauf (V1.4.1)

Nach \`b\` (Sitzplatzbestätigung) kann der Benutzer im privaten Chrome-Fenster **manuell** auf „In den Warenkorb“ gehen. Mit \`c\` + Enter in derselben laufenden \`seat-review\`-Sitzung untersucht der Worker den Warenkorb **nur lesend**. Er verlangt eine einzige Buchung „Reservierung Comfort Class“, Menge 1, WB 1009, Strecke Wien Meidling → Wiener Neustadt, 18:22–18:49, das geprüfte Datum, den unmittelbar zuvor bestätigten Sitzplatz, mindestens zwei Preisangaben ausschließlich 0,00 EUR, Gesamtsumme 0,00 EUR, genau eine AGB-Checkbox und einen eindeutig bezeichneten Abschlussbutton auf dem offiziellen HTTPS-Checkout. Nicht eindeutige Daten blockieren die Prüfung. Die Prüfung klickt **weder** AGB noch Warenkorb noch „Zahlungspflichtig bestellen“. Strukturierte Diagnose ohne Konto- oder Ticketnummern.

Diese Funktion ist **noch keine vollautomatische Buchung**: Der heutige Browser-Worker kann nicht vollständig und belastbar nachweisen, dass keine vorhandene Reservierung zum Datum existiert (Kontobestand liefert \`inventoryComplete:false\`), und die tatsächliche WESTbahn-Bestätigungsseite mit echter Anbieter-Buchungsnummer ist noch nicht live getestet. Der bestehende Wochenlauf mit 0-EUR-Freigabe bleibt deswegen ohne separat geprüften Anbieteradapter gesperrt. Ein sichtbarer Betrag von 0,00 EUR, ein Sitzplatzdialog oder ein Warenkorb sind **kein** bestätigtes Ticket. Für die vollständige Automation fehlen Live-Tests für Dublettenprüfung, einmaliges Absenden, Bestätigung und Wiederanlauf nach Zeitüberschreitungen. Keine Zugangsdaten im GitHub-Repository speichern.

Tests (im Server-Container): \`cd /app/server/browser && /opt/agent-venv/bin/python -m unittest test_checkout_guard.py test_worker.py\`.


## Schutz für bereits gekaufte Fahrten (11.11.2026)

Vom Nutzer nachweislich selbst gekaufte Reservierungen können ohne erneuten WESTbahn-Checkout im Server-Ledger als \`user_reported\` eingetragen werden. Dieses Flag ist **keine** vom Anbieter bestätigte Buchungsnummer und erscheint deswegen nicht in \`confirmedThrough\`. Es verhindert jedoch, dass der automatische Wochenlauf für denselben Tag nochmals buchen würde. Die Eintragung erfordert den bestehenden, authentifizierten AgentZentrale-Server und einen gesonderten ausdrücklichen Bestätigungswert.

**Beispiel für die am 17.11.2026 bereits erworbene Reservierung, Sitz 191D:**

\`\`\`bash
sudo bash -c 'cd /opt/agentzentrale && docker compose exec -T agentzentrale node /app/server/book-existing.mjs 2026-11-17 191D --confirm-existing'
\`\`\`

Der Befehl ist idempotent für identische Datum-/Platzwerte und verweigert widersprüchliche Änderungen. Er kauft kein Ticket und liest kein Passwort aus dem Terminal. Er nutzt das Serverzugangstoken ausschließlich containerintern.

**Lesende Kontoprüfung auf eine möglicherweise bestehende Reservierung:**

\`\`\`bash
sudo bash -c 'cd /opt/agentzentrale && docker compose exec -T agentzentrale /opt/agent-venv/bin/python /app/server/browser/worker.py booking-check --date 2026-11-17 --seat 191D'
\`\`\`

Der Aufruf setzt ein geschlossenes privates \`seat-review\`-Browserfenster voraus und liest die sichtbaren gültigen Tickets über die gespeicherte Anmeldung. Ausgabe \`existing_ticket_visible\` bedeutet eine passende Konto-Karte (bei fehlendem Jahr nur möglicherweise passend). \`not_seen_in_incomplete_account\` bedeutet **niemals**, dass die Strecke frei von Buchungen ist. Beide Ergebnisse führen zu \`safeToBook:false\`. Ohne vollständige Bestandsprüfung und echte Anbieter-Bestätigung bleibt die Live-Buchungsautomatik gesperrt.

**Tests nach dem Server-Update:**

\`\`\`bash
sudo bash -c 'cd /opt/agentzentrale && docker compose exec -T agentzentrale sh -c "cd /app/server && node --test tests/*.test.mjs && cd browser && python -m unittest test_booking_evidence.py test_checkout_guard.py test_worker.py"'
\`\`\`

Die neue Bestandsprüfung ist fail-closed. Sie dient als Voraussetzung für einen späteren vollständig verifizierten Checkout-Adapter, nicht als bereits funktionierender automatischer Kauf.


## Visuelle Sitzplatz-Ändern-Erkennung (11.11.2026)

Falls die WESTbahn-Oberfläche den Sitzplatz-Link in einer anderen DOM-Spalte als die Überschrift platziert und beide zusammen mit dem Warenkorb unter demselben Layout-Container liegen, verwendet der Agent einen zusätzlichen, **eng begrenzten visuellen** Fallback. Er verlangt eine sichtbare Sitzplatzüberschrift, eine zugehörige Wagen-/Platz-Zusammenfassung sowie genau ein an derselben Bildschirmzeile ausgerichtetes klickbares „Ändern“-Element. Das weiter oben liegende „Bearbeiten“ der Reisedaten und beliebige Warenkorb-Buttons dürfen nicht gewählt werden. Bei mehreren oder fehlenden Treffern wird abgebrochen. Tests für eine gemischte Grid-Zeile und ein fehlendes Sitzplatzfeld sind ergänzt. Der echte WESTbahn-Live-Test dieser verbesserten Erkennung steht noch aus.


## Datumsprüfung und App-Status (11. November 2026)

Die Kontokarte im echten Test für 17.11.2026 / 191D wurde als `existing_ticket_visible` erkannt, aber ohne ausdrückliche Jahresangabe (`dateFullyVerified:false`). Das ist korrekt und kein Beleg eines vollständigen Buchungsbestands. Die Bestandsprüfung kann jetzt zusätzlich ein explizites Reisedatum im Format TT.MM.JJJJ aus eindeutig benannten Feldern „Fahrtdatum“, „Reisedatum“ oder „Abfahrt“ derselben sichtbaren Ticketkarte lesen. Andere Datumsangaben wie „Kaufdatum“ dürfen **nicht** als Reisedatum interpretiert werden. Bei mehreren unterschiedlichen vollständigen Reisedaten wird keine eindeutige Jahresbestätigung angenommen.

Der Android-WESTbahn-Bildschirm kennzeichnet `user_reported` als **„Bereits gebucht (gemeldet)“**; dieser Schutzstatus wird nicht als offizielle Buchungsbestätigung ausgegeben. Ein neuer Android-Build ist separat erforderlich, um die Anzeige in einer installierten APK zu sehen.

Zum Prüfen der Änderungen im aktualisierten Container:

```bash
cd /app/server/browser
python -m unittest test_booking_evidence.py test_checkout_guard.py
```

Es erfolgen keine Buchungen, keine Warenkorbänderungen und keine automatischen Käufe. `safeToBook` bleibt bei der Bestandsprüfung absichtlich `false`, solange ein vollständiger Anbieterabgleich fehlt.


## Bestätigungsnachweis aus vorhandenen Tickets (11.11.2026)

Der neue rein lesende Modus **confirmation-check --date YYYY-MM-DD --seat 191D** durchsucht im angemeldeten WESTbahn-Konto auf den offiziellen Domains sichtbare Karten bereits gekaufter Comfort-Reservierungen. Er prüft innerhalb der Ticketkarte Datum, Sitzplatz, Strecke und beschriftete Felder wie „Buchungsnummer“, „Bestellnummer“, „Reservierungsnummer“, „Auftragsnummer“ und „Ticketnummer“. Diese Nummern werden **nie ausgegeben**; nur boolesche Merkmale verlassen den Parser.

Die Ergebnisebenen sind **dated_reference_candidate** (Reisejahr und beschriftete Referenz), **visible_ticket_card** (passende Karte ohne vollständigen Jahres-/Referenznachweis) und **not_proven** (keine passende Karte im unvollständigen Bestand, keinesfalls ein Nachweis für Nichtvorhandensein).

**confirmationVerified:false**, **inventoryComplete:false** und **bookingAuthorized:false** bleiben unverändert. Der Modus klickt keine Bestell- oder Kaufbuttons und erklärt keinen Kauf als erfolgreich. Eine belastbare Abschlussprüfung benötigt eine noch nicht implementierte verifizierte Anbieterbeleg-Verarbeitung.

Tests im Container: cd /app/server/browser && python -m unittest test_confirmation_evidence.py test_booking_evidence.py test_checkout_guard.py

Read-only Echtprüfung: python worker.py confirmation-check --date 2026-11-17 --seat 191D



## Bestehende WESTbahn-Ticketdetails nur lesen

Der neue Modus **ticket-detail-check** untersucht eine bereits vorhandene Comfort-Reservierung (z. B. 17.11.2026, Platz 191D). Er durchsucht die ersten beiden Seiten der gültigen Tickets auf den offiziellen WESTbahn-Domains. Bei einer passenden Ticketkarte akzeptiert er nur einen eindeutig bezeichneten, statischen HTTPS-Link zu einer reinen Ticket-Detailansicht innerhalb des gleichen WESTbahn-Hosts. Nur dann öffnet er diese Adresse per **GET** in einer neuen Browserseite. **Es werden keine Buttons angeklickt, keine Formulare versendet, keine Dateien heruntergeladen und keine Buchungen geändert.**

Bei fehlendem oder mehrdeutigem Link stoppt der Modus mit **no_unique_safe_detail_link** und meldet ausschließlich Diagnosemerkmale, niemals private Links oder Ticketnummern. Selbst wenn ein vollständig datierter Beleg gefunden wird, bleiben **confirmationVerified:false**, **bookingAuthorized:false**, **safeToBook:false** und **inventoryComplete:false**. Die Prüfung ersetzt keine verifizierte Checkout-Bestätigung oder vollständige Dublettenprüfung.

Auf dem Server nach Docker-Update zunächst Tests, dann eine lesende Echtprüfung:

```bash
cd /app/server/browser
python -m unittest test_ticket_detail_view.py test_confirmation_evidence.py test_booking_evidence.py
python worker.py ticket-detail-check --date 2026-11-17 --seat 191D
```

Im Terminal können u. a. **detail_read** (eindeutige erlaubte Detailansicht untersucht), **no_unique_safe_detail_link** (kein sicherer Link), **ticket_not_visible** (keine eindeutig gefundene Karte; keine Aussage zur Verfügbarkeit) oder **detail_unavailable** erscheinen. Das Jahr kann nur bestätigt werden, wenn die Detailansicht einen ausdrücklich genannten Reisetag mit vollständigem Jahr, Strecke, Uhrzeiten, Comfort-Produkt und genau dem gewählten Sitzplatz zeigt. Keine automatischen Ticketkäufe.


## Link-Diagnose für bestehende Tickets

Wenn `ticket-detail-check` ein bereits gebuchtes Ticket erkennt, aber keine eindeutig erlaubte Detailadresse findet, enthält die Ausgabe jetzt zusätzliche **anonymisierte Kategorien**: `rejectionReasons` (z. B. `no_static_destination`, `non_link_detail_control`, `unrecognized_detail_path`, `unrecognized_query`) und `controlKinds` (`anchor`, `button`, `custom_control`). Diese Felder enthalten lediglich Zähler und feste Bezeichnungen, niemals Ticketlinks, Identifikatoren oder Kundendaten. Ein `button` wird **nicht** automatisch angeklickt. Die bisherigen Sicherheitsregeln bleiben unverändert: keine Umbuchung, Stornierung oder Zahlung; fehlende Treffer erlauben keine neue Buchung.

Auf dem aktualisierten Server: `python -m unittest test_ticket_detail_view.py` und danach `python worker.py ticket-detail-check --date 2026-11-17 --seat 191D`. Erst das reale Diagnoseergebnis entscheidet, ob ein Detailaufruf sicher unterstützt werden kann.


## Anonymisierte Pfad-Diagnose für bisher unbekannte Detail-Links

Nach der Live-Prüfung vom 11.11.2026 waren für das Ticket vom 17.11.2026 zwei Schaltflächen und zwei Links sichtbar; die Links wurden wegen eines unbekannten Zielpfads abgelehnt. Der neue `ticket-detail-check` ergänzt die Liste `candidatePathPatterns`. Sie besteht nur aus festen technischen Pfadwörtern (z. B. `ticketshop`, `dashboard`, `tickets`) sowie der Maske `[opaque]` für alle anderen Segmente. Abfrageparameter werden ausschließlich als `none`, `known_only` oder `includes_other_keys` klassifiziert. Echte URLs, IDs, Namen, E-Mail-Adressen und Werte werden nicht ausgegeben.

Die Sicherheitsentscheidung ist unverändert: Ein unbekannter Pfad wird **nicht geöffnet**. Die Diagnose ist ausschließlich dazu gedacht, nach einem echten Test den konkreten Routing-Typ zu erkennen und erst danach die statische Allowlist gezielt zu erweitern. Sie aktiviert keine Bestellungen, Umbuchungen oder Stornierungen.

Testkommando: `python -m unittest test_detail_route_diagnostics.py test_ticket_detail_view.py`.


## Live beobachtete Zwei-Token-Detailroute (November 2026)

Der Konto-Test mit 15 erfolgreichen Tests fand für die vorhandene Reservierung vom 17.11.2026 den anonymisierten Linkpfad `/ticketshop/dashboard/ticket/[opaque]/[opaque]` auf zwei Konto-Karten. Die Ticketdetailprüfung erlaubt diese eng begrenzte **GET-Detailansicht** nun nur dann, wenn der Link eindeutig zur passenden Comfort-Ticketkarte gehört, ausdrücklich als `Details`, `Ticketdetails`, `Ticket ansehen`, `Ticket anzeigen` oder `Reservierung ansehen` bezeichnet ist, die beiden URL-Komponenten jeweils mindestens zwölf zulässige Tokenzeichen enthalten, beide von demselben offiziellen WESTbahn-Host stammen, keine Abfrageparameter/Fragmente vorhanden sind und keine bekannten Verwaltungs- oder Kaufbegriffe in den Pfadkomponenten vorkommen.

Beim Öffnen der Detailseite blockiert eine zusätzliche Netzwerksperre sämtliche Methoden außer GET/HEAD und fremde Top-Level-Zieladressen. Bei mehrdeutigen Links oder nicht eindeutig lesbaren Ticketinformationen wird abgebrochen. Keine Schaltflächen werden angeklickt, und es werden keine Buchungen angelegt, bezahlt, storniert oder verändert. **Eine Seitenadresse allein beweist nicht, dass die Detailansicht tatsächlich korrekt ist:** Der Live-Test und die Prüfung der tatsächlichen Ticketdetails stehen noch aus. Die Flags `confirmationVerified:false`, `safeToBook:false`, `bookingAuthorized:false` und `inventoryComplete:false` werden weiterhin nicht freigegeben.

Nach Git-Pull: `cd /app/server/browser && python -m unittest test_ticket_detail_view.py test_detail_route_diagnostics.py`. Nur bei erfolgreichen Tests: `python worker.py ticket-detail-check --date 2026-11-17 --seat 191D`.


## Anonymisierte Kennungsstruktur in abgelehnten Ticket-Links

Nach der Live-Prüfung vom 11.11.2026 (`no_unique_safe_detail_link`, zwei Links mit `/ticketshop/dashboard/ticket/[opaque]/[opaque]`) wird nun für **genau diese Linkstruktur** zusätzlich `ticketRouteShape` ausgegeben. Beispiel: `4-7|12-90;token_ascii` bedeutet, dass der erste Pfadbestandteil eine 4- bis 7-stellige und der zweite eine 12- bis 90-stellige Kennung hat, beide aus ASCII-Buchstaben, Ziffern, Bindestrich oder Unterstrich. `other_or_encoded` weist nur auf andere oder kodierte Zeichen hin. Es werden **keine** Kennungen, echten URLs, Abfragewerte, Namen oder exakten Tokenlängen ausgegeben.

Weder diese Diagnose noch ein neues URL-Muster autorisiert eine Buchung oder einen unbekannten Detailaufruf. Die bestehende strenge GET-Allowlist und der Doppelbuchungsschutz bleiben unverändert. Die aktuelle Ausgabe entscheidet erst, ob und wie die Navigationsprüfung weiter angepasst werden kann.

Nach Update: `python -m unittest test_detail_route_diagnostics.py test_ticket_detail_view.py`, danach `python worker.py ticket-detail-check --date 2026-11-17 --seat 191D`. Bei fehlgeschlagenen Tests wird die Echtprüfung nicht gestartet.


## Präzise URL-Grenzen nach Live-Diagnose vom 11.11.2026

Die anonyme Echtprüfung meldete für die vorhandene Ticketkarte `ticketRouteShape: "8-11|4-7;token_ascii"` und einen Link der Struktur `/ticketshop/dashboard/ticket/[opaque]/[opaque]`. Deshalb akzeptiert die bestehende **rein lesende** Ticketdetailprüfung jetzt ausschließlich **8–11** Zeichen im ersten und **4–7** Zeichen im zweiten Pfadbestandteil, jeweils ASCII-Buchstaben/Ziffern/Bindestrich/Unterstrich. Bisherige simulierte 12+-Zeichen-IDs wurden als ungültige Testannahme korrigiert. Tests prüfen die neuen Grenzwerte sowie weiterhin nicht erlaubte längere/kürzere IDs, gefährliche Aktionsnamen, fremde Hosts, Query-Strings und Fragmente. Nur die eindeutig als „Details“ bzw. als reine Ticketansicht bezeichnete URL aus der passenden existierenden Kontokarte darf per GET geöffnet werden; der Browser blockiert schreibende Anfragen.

Die Live-Verifikation dieser aktualisierten Regeln steht noch aus. Der Modus kann niemals eine Bestellung auslösen oder `safeToBook` oder `confirmationVerified` auf `true` setzen. Bei Unklarheiten bleibt die Aktion gesperrt.


## Unterscheidung der Rest-Sperre im echten Kontotest (11.11.2026)

Der Live-Test mit den jetzt passenden URL-Längen (8–11 / 4–7 Zeichen) ergab `non_readonly_ticket_route`. Das heißt: Der Link hat die erwartete URL-Form, scheitert jedoch an einer zusätzlichen Sicherheitsregel. Die Diagnose wurde präzisiert, ohne einzelne Ticket-URLs oder Kennungen auszugeben:

- `ticket_view_caption_not_allowlisted`: angezeigte Beschriftung enthält einen Detail-Hinweis, stimmt aber nicht exakt mit einer freigegebenen reinen Ansicht überein
- `ticket_view_token_safety_filter`: mindestens eine Kennung enthält eine Zeichenfolge, die der Schutzfilter als Verwaltungs-/Kaufbegriff einstuft; auch zufällige Übereinstimmungen sind möglich
- `ticket_view_query_not_allowed`: die beobachtete reine Ticketdetail-Route enthält unerwartete Abfrageparameter
- `ticket_view_other_policy_block`: eine andere Regel verweigert den Link

**Diese Änderung schaltet keine neuen Links oder Kaufaktionen frei.** Sie benennt nur die Blockadeursache und ist daher auch bei unerwarteten Anbieterdaten sicher. Die bestehenden `safeToBook:false`, `bookingAuthorized:false` und `confirmationVerified:false` bleiben unverändert. Im nächsten Echtlauf ist nur `rejectionReasons` nötig, um den nächsten sicheren Schritt zu bestimmen.


## Freigegebene reine Ansicht-Beschriftungen

Nach dem echten Kontotest mit `ticket_view_caption_not_allowlisted` wurde die **enge** Liste bekannter Lesefunktionen erweitert: beispielsweise `Mehr Details`, `Details ansehen`, `Weitere Details`, `Ticketdetails anzeigen`, `Reservierungsdetails ansehen` und `Zur Ticketansicht`. Mehrere Leerzeichen und dekorative Pfeile am Ende werden normalisiert. Nur eine **passende Konto-Ticketkarte** mit genau der beobachteten URL-Struktur (8–11 / 4–7 ASCII-Zeichen), gleichem offiziellen WESTbahn-Host und ohne Query/Fragment darf mit einer dieser Beschriftungen gelesen werden. Mutierende Aktionen (z. B. `Umbuchen`, `Stornieren`, `Zahlungspflichtig bestellen`) bleiben explizit verboten. Unbekannte Beschriftungen bleiben gesperrt.

Die Änderung ist noch nicht live verifiziert. Selbst bei `detail_read` bleiben `bookingAuthorized:false`, `safeToBook:false`, `confirmationVerified:false` und `inventoryComplete:false`. Eine rein lesende Detailprüfung ist keine automatische Buchung.


## Diagnose tatsächlich geladener Ticketdetailseiten

Der Live-Test am 11.11.2026 bestand **22 Tests** und fand **eine erlaubte Detail-URL**. Die HTML-Antwort war lesbar (`detailStatus:detail_read`), enthielt aber **keinen** nachweisbaren Sitzplatz, keine eindeutig passende Strecke/Uhrzeit, keine Buchungsreferenz und kein vollständiges Fahrtdatum. Damit ist **nicht** belegt, dass der Inhalt die richtige Ticketdetailseite war. Ein HTTP-200-Ergebnis allein bedeutet ausdrücklich **keine** verifizierte Reservierung.

Der neue Diagnoseschritt liest nach dem Laden der reinen Detailseite bei fehlenden Inhalten ein zweites Mal nach einer kurzen, begrenzten Wartezeit. Er liefert nur `contentDiagnostics` mit **pageKind** (z. B. `login_required`, `account_overview`, `empty_or_loading`, `embedded_document`, `ticket_content_present`, `partial_ticket_content` oder `unrecognized_content`), `documentType`, einer groben Größenklasse und festen booleschen Indikatoren. Es werden **keine** HTML-Texte, Kennungen, Links, Buchungsnummern oder Datums-/Sitzplatzwerte ausgegeben. Ein frei lesbares Datum irgendwo in der Seite gilt nicht automatisch als Reisedatum. Die bestehenden strengeren Verifikationen bleiben aktiv.

Tests nach Docker-Build: `python -m unittest test_ticket_content_diagnostics.py test_ticket_detail_view.py test_detail_route_diagnostics.py`.

Reine Echtprüfung: `python worker.py ticket-detail-check --date 2026-11-17 --seat 191D`.

Auch wenn `pageKind:ticket_content_present` erscheint, darf erst eine eindeutige Verbindung zwischen Fahrtdatum, Sitzplatz, Strecke, Produkt und Buchungsnachweis als zusätzliche Evidenz betrachtet werden. **`confirmationVerified:false`, `bookingAuthorized:false`, `safeToBook:false`, `inventoryComplete:false`** bleiben gesetzt. Kein automatischer Kauf.


## Sicherheitsprüfung des Bestellabschlusses (11.11.2026)

Die serverseitige Buchungssteuerung in `server/westbahn.mjs` prüft jetzt **vor einem Checkout**, dass ein künftig angeschlossener Anbieteradapter die Anmeldung und einen **vollständigen** Buchungsbestandsabgleich explizit bestätigt (`accountVerified:true`, `inventoryComplete:true`, `status:'none'`). Eine bloß leere oder unvollständige Liste ist kein Nachweis, dass noch kein Ticket existiert.

Ein bereits gekauftes Ticket darf der Anbieteradapter über `status:'confirmed'` melden, aber nur mit authentifizierter Anbieter-Kontoevidenz (`receiptSource:'provider_account'`), vollständigem Abgleich und einem exakt passenden Receipt (Datum, Strecke, Abfahrt, Comfort 2+, KlimaTicket, Sitzplatz, 0 Euro, Buchungsnummer). Ein bereits belegter Sitzplatz muss nicht nochmals als `available` gelten; bestehende Tickets werden so auch nach dem Kauf korrekt erkannt.

**Nach einer künftig autorisierten 0-Euro-Buchung** muss der Adapter zusätzlich das Anbieter-Konto erneut und unabhängig von seiner `book()`-Antwort lesen. Erst ein **identischer** Buchungsbeleg mit derselben Buchungs-ID und allen Reisedaten darf als `confirmed` gespeichert werden. Ein Erfolgsbanner oder eine Cart-Summe von 0 Euro genügt nicht. Bei fehlender, anderer oder nicht erreichbarer Bestätigung wird die Fahrt **`uncertain`** und darf nie automatisch wiederholt werden – auch nicht nach einem Neustart. Der vorhandene persistente Buchungsstatus wird vor dem ersten tatsächlichen Kaufversuch geschrieben. Bereits als `user_reported` geschützte Buchungen, insbesondere **17.11.2026 / 191D**, bleiben unverändert.

Beim Docker-Build wird nun automatisch `node --test server/tests/westbahn.test.mjs` ausgeführt. Ein fehlgeschlagener Test lässt den Build scheitern, bevor der neue Container ersetzt wird. Zusätzlich kann im Container mit `node --test /app/server/tests/westbahn.test.mjs` geprüft werden. Die Browser-Evidenztests werden weiterhin gesondert über Python ausgeführt.

**Noch keine Live-Buchung:** Im Repository ist kein verifizierter Provider-Adapter installiert. Die vorhandenen Konto-Leseprüfungen sind nicht mit dem zahlungspflichtigen Bestellbutton verbunden. Es wird durch diese Änderung **kein** Kauf ausgelöst, und die wöchentliche Vollautomatik bleibt deaktiviert.


## Privater Abgleich einer erwarteten Buchungsnummer

Zusätzlich zur bereits erfolgreichen Ticketdetailprüfung kann die interne Python-Funktion `inspect_existing_ticket_details(context, day, seat, expected_booking_id=...)` nun optional eine **bereits intern bekannte erwartete Buchungs-ID** vergleichen. Dafür müssen der volle Reisetag mit Jahr, Strecke, Fahrzeiten, Comfort-Produkt und der Sitzplatz passen; auf der Ticketdetailseite muss eine **eindeutig beschriftete** und exakt gleiche Buchungsreferenz stehen. Unter anderem unbeschriftete, zu kurze, abweichende oder widersprüchliche Kennungen werden abgelehnt. Die Rückgabe enthält nur `bookingReferenceChecked` und `bookingReferenceMatched` als boolesche Werte, niemals die Kennungen selbst. Der normale Kommandozeilenmodus `ticket-detail-check` ruft weiterhin **keine** Buchung ab und benötigt keine Buchungsnummer im Terminal.

Dies ist eine **interne Vorarbeit** für einen künftigen verifizierten Adapter, kein installierter WESTbahn-Kaufadapter. Auch ein Treffer allein hebt die Vollständigkeitssperre `inventoryComplete:false` nicht auf und setzt `bookingAuthorized` nicht auf `true`. Die Bestandsprüfung bleibt ohne nachweislich vollständigen Abgleich blockiert. Der Docker-Build prüft die reine Referenzfunktion mit `python -m unittest -q test_booking_reference_match.py`. Vollständige Browserregression: `cd /app/server/browser && python -m unittest test_booking_reference_match.py test_ticket_detail_view.py test_ticket_content_diagnostics.py test_detail_route_diagnostics.py`.

**Wichtig:** Keine Buchungsnummer über eine Kommandozeile als Argument, eine öffentliche API oder in Debug-Ausgaben übermitteln. Ein künftiger Adapter muss den erwarteten Wert ausschließlich intern und vertraulich an die Prüf-Funktion übergeben.


## AgentZentrale: Android- und Gateway-Anbindung für vorhandene Tickets

Der Backend-Browser ist jetzt über den authentifizierten API-Endpunkt `POST /westbahn/browser/audit-ticket` erreichbar. Er akzeptiert ausschließlich `{"date":"JJJJ-MM-TT","seat":"191D"}` für einen im aktuellen Pendelplan liegenden Reisetag. Beim Aufruf wird der vorhandene Python-Modus `ticket-detail-check` mit dem geschützten, angemeldeten Serverprofil ausgeführt. Kein Zugangscode, Ticket-Link und keine Buchungsreferenz gehen an die Android-App; das Gateway gibt ausschließlich boolesche Merkmale zurück. Die Prüfzeit ist begrenzt, während der Prüfung wird kein paralleler Browserlauf gestartet.

Ein nach Anbieter-Kontoevidenz **positiv geprüftes bestehendes Ticket** setzt den neuen persistenten Protokollstatus `existing_verified`. Dieser Status blockiert jeden späteren automatischen Checkout für denselben Tag, auch nach Server-Neustart. Ein nur sichtbarer oder unklarer Ticketkarteneintrag setzt **keine** solche Bestätigung, und ein fehlender Treffer wird niemals als Beweis für eine freie Buchung behandelt. Widersprüchliche Sitzplätze werden nicht automatisch überschrieben, laufende oder ungewisse Buchungen behalten ihren strengeren Schutzstatus. Der Ticket-Check führt weder Buchung noch Storno aus und lässt `bookingAuthorized:false`, `confirmationVerified:false`, `safeToBook:false`, `inventoryComplete:false` unverändert.

Die Android-Oberfläche enthält hierfür unter „Cloud-Browser“ Datum, Sitzplatz und „Ticket nur lesend prüfen“. Das erfordert eine **aktualisierte App-Version**; die Serveränderung allein aktualisiert keine bestehende APK. Das Gateway muss wie bisher mit dem gespeicherten Zugriffsschlüssel verbunden sein, der Browser mit gültigem WESTbahn-Profil muss aktiviert sein. Die Oberfläche meldet separat, ob das Ticket tatsächlich ins lokale Buchungsprotokoll als geschützt übernommen wurde.

Pflichtprüfungen beim Docker-Build: `node --test server/tests/westbahn.test.mjs server/tests/browser_audit.test.mjs server/tests/browser_route.test.mjs`. Der Build scheitert bei fehlerhaften API-Autorisierungen, unzureichender Evidenz oder fehlendem Sperrschutz. Die Tests verwenden ausschließlich simulierte Antworten, **keine** echten WESTbahn-Bestellungen. Eine vollständige Inventarprüfung und ein autorisierter Checkout-Adapter fehlen weiterhin. Die 0-Euro-Automatik bleibt **deaktiviert**.


## Sammelprüfung der nächsten fünf Pendeltage (11. November 2026)

Die AgentZentrale kann über `POST /westbahn/browser/audit-week` eine **authentifizierte, rein lesende** Kontoprüfung für die **nächsten fünf geplanten Werktage** starten. Der Server ermittelt diese Daten selbst anhand der Zeitzone `Europe/Vienna`, statt beliebige Datumswerte aus der App zu akzeptieren. Das Python-Kommando `inventory-batch --dates JJJJ-MM-TT,...` liest vorhandene Konto-Ticketkarten auf `westbahn.at` und `westbahn.de` mit einer Obergrenze von fünf Seiten je Domain. Geschützte Buchungsinhalte und Referenzen verlassen den Browserprozess nicht.

Im Ergebnis erscheinen pro Tag ausschließlich eine dieser festen Kategorien: `visible_year_verified` (passende sichtbare Karte mit konkreter Jahresangabe), `possible_existing` (passende Karte ohne eindeutiges Jahr) oder `review_required` (kein nachgewiesener Treffer). Sichtbare Platznummern und Datum werden angezeigt; Kontonamen, Ticketcodes, Buchungsnummern, HTML und URLs nicht. Auch die fehlgeschlagene Kontoprüfung wird mit `review_required` gemeldet. Die API entfernt unbekannte Datenfelder und ignoriert unplausible Anbieterantworten. Ein fehlender sichtbarer Eintrag beweist **niemals** die Abwesenheit einer Reservierung.

Die neue Android-Oberfläche hat die Schaltfläche **„Nächste 5 Pendeltage prüfen“**. Eine aktualisierte APK ist für die neue Schaltfläche erforderlich; die serverseitige API kann unabhängig davon getestet werden. Die Browserautomatik sperrt POST/PUT/PATCH/DELETE während dieser Bestandslesung. **`inventoryComplete:false`, `safeToBook:false`, `bookingAuthorized:false`** bleiben immer gesetzt; keine Buchung und keine automatische Freigabe wegen einer fehlenden Karte. Eine positive Karte in diesem Sammelcheck setzt noch keinen bestätigten Buchungsstatus; dafür ist weiterhin die separate eindeutige Ticketdetailprüfung nötig.

Docker-Build: `python -m unittest -q test_booking_reference_match.py test_inventory_batch.py` und `node --test server/tests/westbahn.test.mjs server/tests/browser_audit.test.mjs server/tests/browser_route.test.mjs`. Die Tests verwenden ausschließlich synthetische Tickets und starten keinen Kauf.


## Zweitprüfung für bestehende Fahrten im Fünf-Tage-Scan

Der Konto-Sammelcheck vom 11.11.2026 fand am 17.11.2026 die Sitzplatzkarte **191D**, jedoch ohne Jahresangabe (`possible_existing`). Für 18., 19., 20. und 23.11. wurden keine eindeutig zuordenbaren Karten erkannt (`review_required`). Das ist **keine** vollständige Bestandsaufnahme und kein Beweis für fehlende Buchungen.

Nach dem Sammeln der sichtbaren Konto-Karten kann `inventory-batch` nun bis zu **zwei** Tage mit jeweils genau **einem** erkannten Platzkandidaten durch `inspect_existing_ticket_details()` nachprüfen. Die vorhandene Funktion liest die offizielle Ticketdetailansicht **ausschließlich per GET**, ohne Kauf, Formularänderung, Klick, Download oder Storno. Ein Tag erhält nur dann `detail_verified`, wenn detaillierte Nachweise übereinstimmen: explizites vollständiges Datum, genau dieser Sitzplatz, Strecke, Fahrzeiten, Comfort-Reservierung, Referenz-Indikator und sämtliche `bookingAuthorized:false`/`safeToBook:false`-Schutzmerkmale. Bei mehreren Sitzen, fehlendem/abweichendem Detail, Loginproblemen oder Timeout bleibt der ursprüngliche vorsichtige Status erhalten. Es werden keine Buchungsnummern, URLs oder Seitentexte an App/API ausgegeben.

Die Android-Anzeige unterscheidet nun `detail_verified` („Ticketdetails vollständig geprüft“) von `possible_existing` und `review_required`. Dieser positive Nachweis betrifft nur **bereits vorhandene** Tickets und bestätigt **keinen** neu ausgelösten Kauf. Der Sammelcheck setzt **keine** Buchungssperre im Ledger und autorisiert keine Neubuchung; die separate `audit-ticket`-Aktion bleibt hierfür zuständig. Auch nach einem `detail_verified` im Sammelcheck gilt unverändert `inventoryComplete:false`, `safeToBook:false`, `bookingAuthorized:false`.

Regressionsprüfungen sind in den bestehenden Docker-Build integriert: `test_inventory_batch.py` sowie `server/tests/browser_audit.test.mjs`. Die neuen synthetischen Tests für richtige und falsche Jahr-/Sitzplatz-/Referenz-Nachweise müssen auf dem Zielserver noch ausgeführt werden.


## Positive Detailprüfung aus dem Sammelcheck im Doppelbuchungsprotokoll sichern

Nach der erfolgreichen echten Sammelprüfung vom 11.11.2026 (`2026-11-17`, Sitzplatz `191D`, `detail_verified`, vier weitere Tage `review_required`) übernimmt die **authentifizierte** API `POST /westbahn/browser/audit-week` nun nur eindeutig positive `detail_verified`-Ergebnisse als geschützte, bestehende Reservierung in das persistente Buchungsprotokoll (`existing_verified`). Dafür müssen Datum, genau ein Sitzplatz, `detailVerified:true`, `dateVerified:true`, `potentialDuplicate:true` und alle gesperrten Buchungsmerkmale zusammenpassen. Die serverseitige Browser-Sanitizer-Funktion kontrolliert die Struktur, bevor der API-Endpunkt sie erhält.

Die Antwort enthält `ledgerProtectedDates` für erfolgreich gesicherte bestehende Tickets und `ledgerReviewDates` für Konflikte. Bereits bestätigte Buchungen werden nicht überschrieben, `booking` und `uncertain` bleiben bestehen und **werden weiterhin als manuell zu prüfende Konflikte angezeigt**, statt durch die sichtbare Detailseite eine Checkout-Bestätigung zu suggerieren. Abweichende Sitzplätze lösen keinen automatischen Austausch aus. Tage mit `possible_existing`, `visible_year_verified` oder `review_required` werden nie als verifiziert gespeichert.

**Wichtig:** Der direkte Python-Terminalbefehl `worker.py inventory-batch` meldet nur die Beweise und schreibt **nicht** in die Node.js-Buchungsdatei. Der dauerhafte Schutz erfolgt nach einem Aufruf des autorisierten API-Endpunkts (beispielsweise mit der neuen Android-Schaltfläche). Die APK benötigt ein separates Release/Update.

Das ist nur eine positive Bestandsprüfung. Keine Negativfreigabe: `inventoryComplete:false`, `safeToBook:false` und `bookingAuthorized:false` bleiben erhalten; es gibt weiterhin **keinen** produktiven WESTbahn-Buchungsadapter. Der Docker-Build testet die Absicherung und den Neustartschutz mit simulierten Account-/Ticketdaten.


## Automatischer Montags-Check (11.11.2026)

`server/weekly-review.mjs` führt die reine WESTbahn-Bestandsprüfung bei laufendem Server jeden **Montag ab 07:00 Uhr, Europe/Vienna** für die nächsten fünf Pendeltage aus, sofern `WESTBAHN_BROWSER_ENABLED=true` und `WESTBAHN_WEEKLY_READONLY_ENABLED` nicht ausdrücklich `false` ist. Datum und Sommerzeit werden mit `viennaClock()` berechnet; ein pro Montag persistierter Zeitstempel `WESTBAHN_REVIEW_STATE` (Standard `./data/westbahn-review.json`) verhindert unbeabsichtigte parallele oder wiederholte automatische Kontoprüfungen nach einem Neustart. Bei Serverausfall vor oder während des Aufrufs erfolgt **kein** automatischer Checkout und kein stiller Ersatzkauf. Falls der Container während des Montags wieder anläuft, kann die noch nicht ausgelöste Prüfung ab 07:00 nachgeholt werden.

Vor jeder Ledger-Änderung wird **der gesamte Bericht** über `sanitizeBatchInventory()` validiert. Nur eindeutige `detail_verified`-Tickets werden mit `recordVerifiedExisting()` gegen Doppelbuchung geschützt. Ein verlorener Login, fehlende Seiten, ein falsches Datum oder ein ungeklärter Sitzplatz bleiben `review_required`, niemals `safeToBook`. Konflikte mit bereits gespeicherten Sitzen und `uncertain`-Bestellvorgängen werden nicht überschrieben.

Die Android-App Version **1.4.5** zeigt die letzte automatische Lesekontrolle und den neuen Statusbildschirm. Die geschützte API `GET /westbahn/review-status` liefert die letzte rein lesende Prüfung. `GET /westbahn/readiness` zeigt den Status der nächsten fünf Fahrtage, die bevorzugten Plätze **233A und 233D** und die noch fehlenden Voraussetzungen (vollständiger authentifizierter Bestandsnachweis, realer Checkout-Adapter, exakter frisch bestätigter 0-Euro-Preis und unabhängig abgeglichener Anbieterbeleg).

`POST /westbahn/browser/audit-week` verwendet denselben sicheren Prüfpfad wie die Montagsautomatik. Manuelles Lesen bleibt erlaubt, selbst wenn `WESTBAHN_WEEKLY_READONLY_ENABLED=false` gesetzt wurde. Der eigentliche Kauf bleibt **deaktiviert**, solange kein verifizierter produktiver WESTbahn-Buchungsadapter existiert und die vollständige Bestandsprüfung nicht möglich ist. `WESTBAHN_BROWSER_ENABLED=true` allein darf kein Ticket buchen.

Die Tests `server/tests/weekly-review.test.mjs`, `server/tests/booking-readiness.test.mjs` und die bestehenden Provider-/API-Tests sind verpflichtend im Docker-Build. Zusätzlich ist in `.github/workflows/android.yml` ein Test-APK-Build für Änderungen unter `src/**` oder `app.json` eingerichtet. Ein erfolgreicher Build oder eine verfügbare APK ist erst nach Bestätigung durch GitHub Actions nachgewiesen; das Repository allein ist kein freigegebenes APK.


## Exakter Sitzplatz- und 0-Euro-Kaufvertrag

Für einen künftig angebundenen echten WESTbahn-Checkout akzeptiert die zentrale Validierung nur `productType: "seat_reservation"`, `quantity: 1`, `ticket: "KlimaTicket Österreich"`, `class: "2+"`, `departure: "18:22"`, exakt Wien Meidling → Wiener Neustadt Hbf, übereinstimmendes Reisedatum und den **genau ausgewählten Sitzplatz**. Der vollständige Warenkorb muss `currency: "EUR"` und `totalCents: 0` enthalten. Die Vorgaben werden sowohl am frischen Angebot als auch am danach abgeglichenen Anbieterbeleg geprüft; ein gewöhnliches Zugticket, zwei Plätze, eine falsche Klasse oder positive Gesamtkosten sind keine autorisierte Buchung.

Sitzplatzpriorität bleibt **233A vor 233D**, danach 191D/182A und nur passende Alternativen ohne Vierertisch; ein Platz ohne eindeutig verifizierte 2+-Klasse, Zweiersitzanordnung oder Verfügbarkeit wird nicht automatisch ausgewählt. Wenn die Struktur der echten WESTbahn-Angebotsseite diese Felder nicht zuverlässig belegt, darf der spätere Adapter sie nicht als Fakten erfinden und muss die Buchung blockieren. Der aktuelle Browser hat nach wie vor **keine** freigegebene Kaufaktion; dieser Vertrag ist zunächst mit synthetischen Tests abgesichert.
