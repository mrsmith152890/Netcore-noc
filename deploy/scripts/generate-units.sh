#!/usr/bin/env bash
# Genera las unidades systemd (usuario netcore, endurecidas). Uso: ./generate-units.sh [directorio_app]
set -euo pipefail
APP="${1:-/opt/netcore-noc}"
BACK="$APP/backend"
OUT="$(cd "$(dirname "$0")/../systemd" && pwd)"

mk() {   # $1 nombre, $2 descripción, $3 comando, $4 capacidades
cat > "$OUT/netcore-$1.service" << UNIT
[Unit]
Description=NetCore NOC - $2
After=network-online.target postgresql.service
Wants=network-online.target postgresql.service
PartOf=netcore.target

[Service]
Type=simple
User=netcore
Group=netcore
WorkingDirectory=$BACK
ExecStart=$3
Restart=always
RestartSec=5
TimeoutStopSec=30
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=HOME=/tmp
Environment=SNMP_PERSISTENT_DIR=/tmp
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
LockPersonality=true
SystemCallArchitectures=native
$4

[Install]
WantedBy=netcore.target
UNIT
}

NOCAP=$'CapabilityBoundingSet='
RAW=$'AmbientCapabilities=CAP_NET_RAW\nCapabilityBoundingSet=CAP_NET_RAW'   # solo para el ping

mk api "API" "$BACK/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000" "$NOCAP"
mk availability "motor de disponibilidad ICMP" "$BACK/.venv/bin/python -m app.workers.availability" "$RAW"
mk snmp "poller SNMP" "$BACK/.venv/bin/python -m app.workers.snmp_poller" "$NOCAP"
mk discovery "worker de descubrimiento" "$BACK/.venv/bin/python -m app.workers.discovery" "$RAW"
mk alerts "alertas y notificaciones" "$BACK/.venv/bin/python -m app.workers.alerts" "$NOCAP"
mk services "comprobaciones de servicios" "$BACK/.venv/bin/python -m app.workers.services" "$NOCAP"
mk watchdog "vigilancia del sistema" "$BACK/.venv/bin/python -m app.workers.watchdog" "$NOCAP"
echo "Unidades generadas en $OUT"
