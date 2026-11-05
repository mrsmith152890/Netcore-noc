#!/usr/bin/env bash
# Restaura el último volcado en una base temporal y comprueba que los datos son coherentes.
# Uso: restore-test.sh [archivo.dump]
set -euo pipefail
DEST=/var/backups/netcore
KEYFILE=/root/.netcore-backup-pass
TESTDB=netcore_restore_test
pg() { runuser -u postgres -- "$@"; }
cleanup() { pg dropdb --if-exists "$TESTDB" > /dev/null 2>&1 || true; }
on_exit() {
  rc=$?
  trap - EXIT
  if [ "$rc" -ne 0 ]; then
    pg psql -d netcore -qc "insert into worker_heartbeats (worker, beat_at, detail) values ('restore_test', now(), 'FALLA: prueba de restauración interrumpida; revisar journal de netcore-restore-test.service') on conflict (worker) do update set beat_at = now(), detail = excluded.detail" || true
  fi
  cleanup
  exit "$rc"
}
trap on_exit EXIT
DUMP="${1:-$(ls -1t "$DEST"/netcore-2*.dump 2>/dev/null | head -1 || true)}"
[ -n "$DUMP" ] && [ -f "$DUMP" ] || { echo "FALLA: no hay volcados en $DEST"; exit 1; }
echo "Probando: $DUMP"
cleanup
pg createdb "$TESTDB"
pg pg_restore --no-owner --no-privileges -d "$TESTDB" < "$DUMP" 2> /tmp/restore-test.log || true

FAIL=0
q() { pg psql -d "$TESTDB" -Atc "$1" 2> /dev/null || echo 0; }
check() {   # nombre, consulta, mínimo
  local v; v=$(q "$2")
  if [ "${v:-0}" -ge "$3" ] 2> /dev/null; then echo "OK     $1 = $v"; else echo "FALLA  $1 = ${v:-?} (mínimo $3)"; FAIL=1; fi
}
check "usuarios" "select count(*) from users" 1
check "sedes" "select count(*) from sites" 1
check "dispositivos" "select count(*) from devices" 1
check "muestras de ping" "select count(*) from ping_samples" 1
check "versión de migraciones" "select count(*) from alembic_version" 1
echo "INFO   migración restaurada: $(q 'select version_num from alembic_version') / en producción: $(pg psql -d netcore -Atc 'select version_num from alembic_version')"

if [ -f "$KEYFILE" ] && ls "$DEST"/netcore-secrets-*.enc > /dev/null 2>&1; then
  S=$(ls -1t "$DEST"/netcore-secrets-*.enc | head -1)
  LIST=$(openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:"$KEYFILE" -in "$S" 2> /dev/null | tar tzf - 2> /dev/null || true)
  if grep -q "backend/.env" <<< "$LIST"; then echo "OK     archivo de secretos legible"; else echo "FALLA  archivo de secretos ilegible"; FAIL=1; fi
fi

age=$(( $(date +%s) - $(stat -c %Y "$DUMP") ))
[ "$age" -lt 93600 ] && echo "OK     el volcado tiene $((age / 3600)) h" || echo "AVISO  el volcado tiene $((age / 3600)) h (más de un día)"

if [ "$FAIL" = "0" ]; then
  date +%s > "$DEST/last-restore-ok"
  RESULT="Restauración correcta; copia verificada"
  echo "RESULTADO: la copia es restaurable"
else
  RESULT="FALLA: la copia no superó las verificaciones; revisar journal de netcore-restore-test.service"
  echo "RESULTADO: FALLA la restauración"
fi
pg psql -d netcore -qc "insert into worker_heartbeats (worker, beat_at, detail) values ('restore_test', now(), '$RESULT') on conflict (worker) do update set beat_at = now(), detail = excluded.detail" || true
exit "$FAIL"
