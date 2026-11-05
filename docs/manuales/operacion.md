# NetCore NOC — manual de operación

## Componentes
| Servicio | Función |
|---|---|
| nginx | HTTPS (443), frontend compilado en /var/www/netcore, proxy hacia la API |
| netcore-api | API (solo 127.0.0.1:8000) |
| netcore-availability | ping y estados UP/DOWN |
| netcore-snmp | interfaces, CPU y memoria |
| netcore-services | comprobaciones TCP/HTTP/DNS |
| netcore-discovery | escaneos de descubrimiento |
| netcore-alerts | reglas, notificaciones y reintentos |
| netcore-watchdog | vigila a todos los anteriores, copias, disco y certificado |
| postgresql | base de datos |
Temporizadores: netcore-backup (02:30), netcore-purge (03:15), netcore-restore-test (domingo 04:30).
Todo corre como el usuario `netcore`, con el código en /opt/netcore-noc (propiedad de root, solo lectura para el servicio).

## Comandos habituales (como root)
- Estado general: `/opt/netcore-noc/deploy/scripts/smoke-test.sh` y la pestaña «Sistema».
- Reiniciar todo: `systemctl restart netcore.target`; uno solo: `systemctl restart netcore-snmp`.
- Logs: `journalctl -u netcore-alerts -f` (o `-u` de cualquier servicio); errores: `journalctl -p err --since "1 hour ago"`.
- Temporizadores: `systemctl list-timers 'netcore-*'`.

## Actualizar el sistema
1. Hacer una copia: `/opt/netcore-noc/deploy/scripts/backup.sh`.
2. Cambiar el código en /opt/netcore-noc y confirmar los cambios con git.
3. `./deploy/scripts/update.sh` (backend) o `./deploy/scripts/update.sh --frontend` (también la interfaz).
4. Verificar con `smoke-test.sh`.

## Copias de seguridad
- Diaria: /var/backups/netcore (volcado de la base + secretos cifrados). Rotación: 7 días, domingos 8 semanas, día 1 de cada mes 12 meses.
- Copia fuera de la VM: SSH (/etc/netcore-backup.conf) y respaldo de la VM en Proxmox.
- La clave que cifra los secretos está en /root/.netcore-backup-pass y debe guardarse además fuera de la VM.
- La restauración se prueba cada domingo. Procedimiento completo: docs/manuales/restauracion.md.

## Usuarios
- Crear o restablecer: `cd /opt/netcore-noc/backend && source .venv/bin/activate && python -m app.cli create-user NOMBRE --role admin` / `python -m app.cli set-password NOMBRE`.
- Roles: viewer (solo lectura), operator (reconoce alertas, edita mapas, lanza escaneos), admin (todo).

## Certificado TLS
Autofirmado (825 días). El vigilante avisa 30 días antes. Para renovar: repetir el comando `openssl req -x509 ...` de la fase 10a
sobre /etc/ssl/netcore, `systemctl reload nginx` y volver a importar el certificado en los equipos de los operadores.

## Si algo falla
| Síntoma | Qué mirar |
|---|---|
| Aviso «Motor / Poller / Servicios / Alertas sin latido» | `journalctl -u netcore-NOMBRE -n 50`; `systemctl restart netcore-NOMBRE` |
| Aviso «API» | `journalctl -u netcore-api -n 50`; `curl localhost:8000/api/v1/health` |
| Aviso «Base de datos» | `systemctl status postgresql`; espacio en disco; `journalctl -u postgresql -n 50` |
| Aviso «Espacio en disco» | `du -xh /var/backups /var/lib/postgresql \| sort -h \| tail`; ajustar retención (NOC_RETENTION_*) |
| Aviso «Copia de seguridad» | `journalctl -u netcore-backup -n 50`; ejecutar `backup.sh` a mano |
| Notificaciones pendientes | Telegram inaccesible o token inválido: pestaña Alertas → Últimos envíos; `journalctl -u netcore-alerts` |
| Cuenta bloqueada | `python -m app.cli set-password USUARIO` |
| La página no carga | `systemctl status nginx`; `nginx -t`; ufw (80 y 443 abiertos) |

## Capacidad
- Muestras de ping: dispositivos × 86 400 ÷ intervalo (10 s) por día, unos 125 bytes cada una. Ver la prueba de carga.
- Si el ciclo de un proceso (Sistema → Latidos) se acerca a su intervalo, subir la concurrencia (NOC_PROBE_CONCURRENCY, NOC_SNMP_CONCURRENCY, NOC_SERVICE_CONCURRENCY).
