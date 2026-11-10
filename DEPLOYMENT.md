# AgentZentrale V1.4 – Server und APK

## Android-Testversion

Der Workflow **Build Android test APK** baut auf main eine Android-Test-APK. In GitHub Actions den erfolgreichen Lauf öffnen und das Artefakt AgentZentrale-Android-test herunterladen. Die APK ist nur eine Testversion; keine Play-Store-Signatur. Ein erfolgreicher Build muss erst verifiziert werden.

## Eigener Docker-Server

Voraussetzungen: Linux-Server mit Docker Compose, HTTPS-Reverse-Proxy und persistentem Datenträger. Keine Zugangsdaten in GitHub speichern.

1. Repository auf dem Server klonen. In dessen Stammverzeichnis:
   `cp server/.env.example server/.env`
2. Einen zufälligen Token (mindestens 24 Zeichen) mit `openssl rand -hex 32` erzeugen und ausschließlich in server/.env als AGENTZENTRALE_ACCESS_TOKEN hinterlegen. Datei mit `chmod 600 server/.env` schützen.
3. `docker compose up -d --build`
4. Die API ist nur über 127.0.0.1:8787 auf dem Host erreichbar. Einen HTTPS-Reverse-Proxy mit eigener Domain und gültigem Zertifikat davor setzen. Den direkten Port nicht öffentlich freigeben.
5. In der App die HTTPS-URL und den eigenen Token konfigurieren. Der Authentifizierungs-Endpunkt /health zeigt, ob der Gateway antwortet.

Der Container läuft ohne Root-Rechte, speichert Browserprofil und Buchungsprotokoll im persistenten Volume agent-data und startet nach einem Serverneustart wieder. Die Server-Konfiguration bleibt außerhalb des Git-Repositories.

## WESTbahn

WESTBAHN_BROWSER_ENABLED standardmäßig false. Erst nach einer bewussten Aktivierung in der lokalen .env und Neustart kann der Browser die offizielle Website für die Suche öffnen. Das vorhandene Browsermodul unterstützt noch keine tatsächliche Buchung, keine Sitzplatzauswahl und keinen Login per Android. Der interaktive Login benötigt einen geschützten grafischen Browserzugang; das Profil darf niemals öffentlich oder in GitHub landen. Für Live-Buchungen sind ein verifizierter Buchungsablauf, reale Preis- und Bestätigungsprüfung sowie die konkrete Nutzerfreigabe erforderlich. WESTBAHN_ADAPTER_MODULE leer lassen, bis ein verifizierter Adapter vorhanden ist.

Öffentliche Projektstandards sind nur Beispieldaten. Persönliche Reisevorgaben erst in der privaten laufenden Konfiguration hinterlegen.

## Hosting

Kein Hosting-Vertrag und kein kostenpflichtiger Dienst wird durch diese Konfiguration angelegt. Ein kostenloser, schlafender Webdienst ohne persistente Festplatte ist für den dauerhaft laufenden Wochenplan und ein gespeichertes Browserprofil ungeeignet. Vor dem Deployment müssen Hosting, HTTPS und Speicher festgelegt werden.
