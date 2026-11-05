#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../systemd"
shopt -s nullglob
cp netcore.target netcore-*.service netcore-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable netcore.target netcore-api netcore-availability netcore-snmp netcore-discovery netcore-alerts netcore-services netcore-watchdog
systemctl enable --now netcore-backup.timer netcore-restore-test.timer netcore-purge.timer
echo "Servicios y temporizadores instalados. Inicia con: systemctl start netcore.target"
