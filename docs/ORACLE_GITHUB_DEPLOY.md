# Oracle-Updates direkt aus GitHub

Diese GitHub Action ersetzt **eine bereits im Oracle-Docker-Container vorhandene** Datei unter `/app/server/browser/*.py`. Sie führt **keine WESTbahn-Buchung** aus, löscht keine Sperrdateien und baut den Container nicht neu. Bestehende Versionen werden vor dem Austausch gesichert; Python-Syntax und SHA-256 werden geprüft.

## Einmalige Einrichtung

Im GitHub-Repository unter **Settings → Secrets and variables → Actions** drei *Repository secrets* anlegen:

- `ORACLE_DEPLOY_HOST`: öffentliche IP oder Hostname des Oracle-Servers
- `ORACLE_DEPLOY_SSH_KEY`: privater SSH-Schlüssel eines **separaten, auf Deployments beschränkten** Schlüsselpaares; der öffentliche Teil muss in `/home/ubuntu/.ssh/authorized_keys` des Servers eingetragen sein
- `ORACLE_DEPLOY_KNOWN_HOSTS`: zuvor **außerhalb von GitHub verifizierter** SSH-Hostschlüssel als known_hosts-Eintrag. Nicht blind per `ssh-keyscan` im Workflow vertrauen.

Danach unter **Actions → Oracle – gezieltes Browser-Update → Run workflow** den Pfad einer einzelnen bestehenden Datei angeben, z. B. `server/browser/worker.py`. Der Server wird mit SSH-Port 22 und Benutzer `ubuntu` angesprochen.

## Schutzmechanismen und Grenzen

- Nur explizit ausgelöste Runs; kein Deploy bei jedem Commit.
- Nur eine vorhandene Python-Datei unmittelbar unter `server/browser/`.
- Vorher: Syntaxprüfung und Docker-Container-Prüfung. Nachher: Syntax-/Hash-Prüfung und Rückspielen des Backups bei Prüfungsfehlern.
- Auf Oracle entsteht ein Backup unter `/home/ubuntu/.agentzentrale-deploy/backups/`.
- Der Patch im Container ist **nicht dauerhaft**: Ein Rebuild kann ihn überschreiben. Eine spätere Migration zum nachvollziehbaren Image-Deployment ist erforderlich.
- Bestehende lokale Änderungen unter `/opt/agentzentrale` werden nicht mit `git pull`, `git reset` oder einem Rebuild überschrieben.
- Der aktuelle private Checkout `checkout_2026112*.py` ist noch **nicht** in diesem öffentlichen Repository. Er sollte keinesfalls ohne Prüfung auf personenbezogene Daten oder Sitzungsdaten öffentlich hochgeladen werden.
- Es gibt derzeit keine automatische Verbindung vom GitHub-Code zu den bereits lokal angepassten Oracle-Checkout-Dateien. Zuerst muss eine sichere private Quellcodeverwaltung samt Abgleich eingerichtet werden.
- Keine unsicheren Wiederholungen von Bestellungen: Bereits nachweislich gebuchte Tage (23. und 24. November 2026) bleiben übersprungen; ein Status `station_selection_blocked` ersetzt keine Buchungsprüfung.
- Niemals API-Keys, Cookies, Browserprofile, App-Passwörter oder SSH-Schlüssel ins GitHub-Repository committen.

Diese Action ist ein **erster Infrastruktur-Schritt**, kein Nachweis eines erfolgreichen End-to-End-Deployments. Vor dem ersten Lauf sind die Secrets zu konfigurieren.
