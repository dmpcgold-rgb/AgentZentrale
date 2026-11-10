#!/usr/bin/env bash
# Run via sudo on the dedicated Ubuntu VM. No cloud resources or paid services are created.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo "Bitte mit sudo ausführen."; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu ]] || { echo "Dieses Skript unterstützt Ubuntu."; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl git openssl
if ! docker compose version >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  arch="$(dpkg --print-architecture)"
  codename="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
  printf '%s\n' "deb [arch=$arch signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $codename stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
install -d -m 0700 /opt/agentzentrale
if [[ ! -d /opt/agentzentrale/.git ]]; then
  if [[ -n "$(ls -A /opt/agentzentrale)" ]]; then
    echo "Zielverzeichnis ist nicht leer. Keine Dateien überschrieben."
    exit 1
  fi
  git clone --branch main https://github.com/dmpcgold-rgb/AgentZentrale.git /opt/agentzentrale
fi
cd /opt/agentzentrale
# Preserve existing .env and persistent Docker volume. Do not enable writes or bookings.
bash deploy/free-vm-setup.sh
echo "Installation abgeschlossen. Der API-Port bleibt lokal gebunden."
echo "Für Android noch HTTPS/VPN und App-Einrichtung erforderlich."
echo "WESTbahn-Livebuchung bleibt deaktiviert."
