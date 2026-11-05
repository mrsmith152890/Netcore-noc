#!/usr/bin/env bash
# Comprobaciones rápidas del despliegue. Termina con código 1 si algo falla.
FAILED=0
ok()   { echo "OK     $1"; }
fail() { echo "FALLA  $1"; FAILED=1; }

for s in netcore-api netcore-availability netcore-snmp netcore-discovery netcore-alerts netcore-services netcore-watchdog nginx postgresql; do
  systemctl is-active --quiet "$s" && ok "servicio $s activo" || fail "servicio $s inactivo"
done
for s in netcore-api netcore-availability netcore-snmp netcore-discovery netcore-alerts netcore-services netcore-watchdog; do
  [ "$(systemctl show -p User --value "$s")" = "netcore" ] && ok "$s corre como netcore" || fail "$s no corre como netcore"
done

code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost/api/v1/health)
[ "$code" = "200" ] && ok "health por HTTPS" || fail "health devolvió $code"
code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/)
[ "$code" = "301" ] && ok "HTTP redirige a HTTPS" || fail "HTTP devolvió $code"
code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost/api/v1/status)
[ "$code" = "401" ] && ok "API protegida (401 sin sesión)" || fail "status sin sesión devolvió $code"
code=$(curl -sk -o /dev/null -w "%{http_code}" https://localhost/)
[ "$code" = "200" ] && ok "frontend servido por nginx" || fail "frontend devolvió $code"
curl -skI https://localhost/ | grep -qi "x-content-type-options" && ok "cabeceras de seguridad presentes" || fail "faltan cabeceras de seguridad"

if ss -ltn | awk '$4 ~ /:8000$/ {print $4}' | grep -qv '^127.0.0.1:'; then
  fail "el puerto 8000 escucha fuera de localhost"
else
  ok "puerto 8000 solo en localhost"
fi
if [ -f /var/backups/netcore/last-success ]; then
  age=$(( $(date +%s) - $(cat /var/backups/netcore/last-success) ))
  [ "$age" -lt 93600 ] && ok "copia de seguridad reciente ($((age / 3600)) h)" || fail "la última copia tiene $((age / 3600)) h"
else
  fail "no hay copias de seguridad todavía"
fi
for m in / /var/backups; do
  use=$(df --output=pcent "$m" | tail -1 | tr -dc 0-9)
  [ "$use" -lt 85 ] && ok "disco $m al ${use}%" || fail "disco $m al ${use}%"
done
exit $FAILED
