# Restauración en un servidor nuevo

Necesitas: el último `netcore-*.dump`, el último `netcore-secrets-*.tar.gz.enc` y la clave de cifrado
(archivo `/root/.netcore-backup-pass` del servidor original, guardada aparte).

1. Ubuntu Server con: `postgresql nginx python3-venv snmp iputils-ping rsync nodejs npm`.
2. Copiar el proyecto a `/opt/netcore-noc`; crear el usuario `netcore` (sin shell); crear el venv e
   instalar `backend/requirements.txt`.
3. Secretos: `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass file:CLAVE -in SECRETOS.enc | tar xzf - -C /`
   (restaura `.env` y `/etc/ssl/netcore`). Permisos: `chgrp netcore .env; chmod 640 .env`.
4. Base de datos (usa la clave de `NOC_DATABASE_URL` del `.env`):
   `sudo -u postgres psql -c "CREATE USER netcore WITH PASSWORD '...'"` y `sudo -u postgres createdb -O netcore netcore`.
5. Datos: `runuser -u postgres -- pg_restore --no-owner --role=netcore -d netcore < netcore-AAAAMMDD-HHMM.dump`
6. `cd /opt/netcore-noc/backend && .venv/bin/alembic upgrade head`
7. `./deploy/scripts/generate-units.sh && ./deploy/scripts/install-services.sh`,
   `./deploy/scripts/build-frontend.sh`, `./deploy/scripts/install-nginx.sh`
8. `systemctl start netcore.target` y `./deploy/scripts/smoke-test.sh`.

Sin `NOC_SECRET_KEY` los tokens de Telegram y las comunidades SNMP guardadas no se pueden descifrar:
habría que volver a registrarlos.
