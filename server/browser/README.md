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

