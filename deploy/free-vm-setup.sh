#!/usr/bin/env bash
# Run on your own Linux VM, from a checked-out AgentZentrale repository.
# Requires Docker Engine + Compose v2 and openssl. Does not provision paid resources.
set -euo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/.."
command -v docker >/dev/null || { echo "Docker Engine fehlt."; exit 1; }
command -v openssl >/dev/null || { echo "OpenSSL fehlt."; exit 1; }
docker compose version >/dev/null
docker info >/dev/null
if [[ ! -f server/.env ]]; then
  token="$(openssl rand -hex 32)"
  sed "s/^AGENTZENTRALE_ACCESS_TOKEN=$/AGENTZENTRALE_ACCESS_TOKEN=$token/" server/.env.example > server/.env
  unset token
fi
chmod 600 server/.env
# Do not overwrite an existing configuration or activate external writes.
docker compose up -d --build
for i in $(seq 1 30); do
  if docker compose exec -T agentzentrale node --input-type=module -e '
    const u="http://127.0.0.1:8787/health";
    const r=await fetch(u,{headers:{Authorization:"Bearer "+process.env.AGENTZENTRALE_ACCESS_TOKEN}});
    if(!r.ok || !(await r.json()).online) process.exit(1);
    const anonymous=await fetch(u);
    if(anonymous.status!==401)process.exit(1);
  ' >/dev/null 2>&1; then
    echo "Gateway erreichbar; anonymer Zugriff abgewiesen."
    break
  fi
  if [[ "$i" == 30 ]]; then echo "Gateway-Test fehlgeschlagen. docker compose logs agentzentrale prüfen."; exit 1; fi
  sleep 2
done
docker compose exec -T agentzentrale /opt/agent-venv/bin/python -c 'import os; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True, executable_path=os.environ["WESTBAHN_CHROMIUM_PATH"]); page=b.new_page(); page.set_content("<title>AgentZentrale</title>"); assert page.title()=="AgentZentrale"; b.close(); p.stop()'
echo "Chromium-Test erfolgreich. API bleibt nur auf dem lokalen Host erreichbar."
echo "Keine echte WESTbahn-Buchung ausgeführt. HTTPS und private Login-Einrichtung fehlen."
