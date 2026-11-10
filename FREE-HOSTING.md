# Kostenloser AgentZentrale-Server (Oracle Cloud Always Free)

## Entscheidung und Grenzen

Oracle Always Free Compute ermöglicht eine Linux-VM mit persistentem Boot-Datenträger. Ampere A1 (arm64) ist für Chromium besser geeignet als eine kleine AMD-Micro-VM mit 1 GB RAM. Die verfügbare kostenlose Kapazität muss im eigenen Konto geprüft werden; idle VMs können zurückgefordert werden. Es gibt keine garantierte Verfügbarkeit für diesen Dienst. Keine kostenpflichtige VM oder Pay-as-you-go-Aktivierung ist erforderlich oder vorgesehen. GitHub Actions bleibt für Software-Builds/Tests, nicht als produktiver Ticket-Buchungsserver.

Offizielle Informationen:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://www.oracle.com/cloud/free/faq/

## 1. Cloud-VM anlegen

1. Ein eigenes Oracle Cloud Free Tier-Konto verwenden (https://signup.oraclecloud.com). Registrierung und Identitäts-/Zahlungskartenprüfung ausschließlich beim Anbieter durchführen.
2. Heimatregion in Europa wählen, falls verfügbar. Always-Free-Instanzen sind auf die Heimatregion beschränkt.
3. Compute-Instanz mit Ubuntu 24.04 LTS ARM64 und VM.Standard.A1.Flex auswählen. Ziel: 1 OCPU, 6 GB RAM, etwa 50 GB Boot-Volume, ausschließlich wenn alle Komponenten im aktuellen Always-Free-Kontingent liegen. Prüfen, dass die Konsole keine kostenpflichtigen Ressourcen anbietet oder verrechnet.
4. SSH-Schlüssel erzeugen bzw. verwenden. Nur SSH-Zugriff aus dem eigenen Netz erlauben. Keine öffentlich erreichbaren Chromium-Debugging-, VNC- oder API-Ports.
5. Docker Engine und Compose v2 nach offizieller Anleitung installieren: https://docs.docker.com/engine/install/ubuntu/

## 2. AgentZentrale installieren

Auf der VM als berechtigter Benutzer:

```bash
git clone https://github.com/dmpcgold-rgb/AgentZentrale.git
cd AgentZentrale
bash deploy/free-vm-setup.sh
```

Nach einer späteren Privatisierung des Repositories ist ein autorisierter GitHub-Zugriff nötig. Das Skript legt bei Bedarf einen zufälligen API-Token in server/.env an, ohne ihn auszugeben. Es startet den Docker-Server und prüft authentifizierten Zugriff, abgewiesene anonyme Zugriffe und den Chromium-Start. Die vorhandene Compose-Konfiguration nutzt ein persistentes Volume und restart: unless-stopped. Das Skript hat noch keinen Test auf einer realen Oracle-VM durchlaufen.

## 3. Sicherer Handy-Zugang

API ausschließlich über einen HTTPS-Reverse-Proxy mit gültigem Zertifikat oder eine private VPN-Verbindung mit HTTPS erreichbar machen. Niemals Port 8787, VNC oder Chrome-Debugging ungeschützt ins Internet öffnen. Den API-Token nur auf dem Server und im geschützten App-Speicher hinterlegen.

## 4. WESTbahn und Betrieb

- WESTBAHN_BROWSER_ENABLED bleibt standardmäßig false; Live-Adapter bleibt leer. Keine Reservierung oder Zahlung wird durch Installation ausgelöst.
- Ein interaktiver geschützter Browserzugang zum einmaligen Login muss noch eingerichtet und auf der realen Website getestet werden. Die persistente Browser-Sitzung und das Buchungsprotokoll bleiben im Docker-Volume.
- Die persönliche Strecke, Sitze, Zeitplan und Preisgrenze werden nur im privaten laufenden System konfiguriert.
- Erst nach verifizierter Echtbuchung und Bestätigung darf der Wochenplan aktiviert werden. Kostenpflichtige Buchungen sind nicht automatisch erlaubt.
- Bei Ausfall oder nicht bestätigter Buchung nicht erneut blind bestellen; zuerst im Kundenkonto abgleichen. Bei Oracle-Reclaim oder fehlender Kapazität auf einen eigenen Rechner oder einen bewusst freigegebenen Hosting-Tarif wechseln.
- OpenAI API-Nutzung ist separat und kann Kosten verursachen; für den reinen Buchungsbrowser ist kein KI-API-Schlüssel zwingend nötig.
