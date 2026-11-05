#!/usr/bin/env bash
# Copia de seguridad: base de datos (pg_dump) + secretos cifrados. Ejecutar como root.
set -euo pipefail
DEST=/var/backups/netcore
DB=netcore
KEYFILE=/root/.netcore-backup-pass
[ -f /etc/netcore-backup.conf ] && source /etc/netcore-backup.conf    # opcional: BACKUP_REMOTE=usuario@host:/ruta

STAMP=$(date +%Y%m%d-%H%M)
install -d -m 700 "$DEST"
umask 077
rm -f "$DEST"/.netcore-*.partial

# 1) base de datos
TMP="$DEST/.netcore-$STAMP.dump.partial"
runuser -u postgres -- pg_dump -Fc --no-owner "$DB" > "$TMP"
pg_restore --list "$TMP" > /dev/null          # el volcado debe poder leerse
mv "$TMP" "$DEST/netcore-$STAMP.dump"

# 2) secretos (.env con la clave de cifrado + certificado), cifrados con la clave de /root
if [ -f "$KEYFILE" ]; then
  tar czf - -C / opt/netcore-noc/backend/.env etc/ssl/netcore \
    | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass file:"$KEYFILE" \
        -out "$DEST/netcore-secrets-$STAMP.tar.gz.enc"
else
  echo "AVISO: no existe $KEYFILE; no se guardaron los secretos" >&2
fi

# 3) rotación: 7 días completos, domingos 8 semanas, día 1 de cada mes 12 meses
now=$(date +%s)
for f in "$DEST"/netcore-*.dump "$DEST"/netcore-secrets-*.enc; do
  [ -e "$f" ] || continue
  d=$(basename "$f" | grep -oE '[0-9]{8}' | head -1)
  [ -n "$d" ] || continue
  iso="${d:0:4}-${d:4:2}-${d:6:2}"
  age=$(( (now - $(date -d "$iso" +%s)) / 86400 ))
  dow=$(date -d "$iso" +%u)
  keep=0
  [ "$age" -le 7 ] && keep=1
  { [ "$age" -le 56 ] && [ "$dow" = 7 ]; } && keep=1
  { [ "$age" -le 365 ] && [ "${d:6:2}" = 01 ]; } && keep=1
  [ "$keep" = 1 ] || rm -f -- "$f"
done

# 4) copia fuera de la VM (opcional). Sin --delete: si aquí se pierde todo, allá se conserva.
if [ -n "${BACKUP_REMOTE:-}" ]; then
  rsync -a -e "ssh -o BatchMode=yes -o ConnectTimeout=15" "$DEST/" "$BACKUP_REMOTE/" \
    || echo "AVISO: falló la copia remota a $BACKUP_REMOTE" >&2
fi

date +%s > "$DEST/last-success"
runuser -u postgres -- psql -d netcore -qc "insert into worker_heartbeats (worker, beat_at, detail) values ('backup', now(), 'netcore-$STAMP.dump') on conflict (worker) do update set beat_at = now(), detail = excluded.detail" || echo "AVISO: no se pudo registrar el latido de la copia" >&2
echo "Copia completada: $DEST/netcore-$STAMP.dump ($(du -h "$DEST/netcore-$STAMP.dump" | cut -f1))"
