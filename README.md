# NetCore NOC

NetCore NOC Manager se distribuye bajo GNU GPL versión 3 solamente (GPL-3.0-only). Consulta el archivo LICENSE. Esta licencia trata de libertades de uso, estudio, modificación y redistribución, no obliga a cobrar ni prohíbe cobrar por copias. Los componentes de terceros conservan sus licencias propias; consulta THIRD_PARTY_NOTICES.md antes de redistribuir bundles.

Plataforma web de monitoreo y operación de redes. Incluye inventario, ping/ICMP, SNMP, mapas de topología, descubrimiento puntual, alertas con Telegram, ventanas de mantenimiento, reportes, auditoría y copias de seguridad verificadas.

## Componentes

- **Frontend:** React, TypeScript y Vite; en producción se sirve como archivos estáticos en `/var/www/netcore` mediante Nginx.
- **API:** FastAPI y SQLAlchemy, escuchando únicamente en `127.0.0.1:8000` detrás de Nginx.
- **Base de datos:** PostgreSQL con migraciones Alembic.
- **Procesos systemd:** disponibilidad ICMP, SNMP, servicios, descubrimiento, alertas y vigilancia del sistema.
- **Seguridad:** sesiones en cookie, roles `viewer`/`operator`/`admin`, credenciales SNMP y Telegram cifradas en base de datos, y registro de auditoría.

## Requisitos

Instalación documentada para Ubuntu Server 24.04 LTS. Se recomienda una VM o servidor con 2 vCPU, 4 GB RAM y almacenamiento acorde al número de dispositivos y la retención. Requiere acceso de administrador al servidor, PostgreSQL local, DNS o un nombre resoluble en la red y un certificado TLS.

Paquetes base:

```bash
sudo apt update
sudo apt install -y git curl ca-certificates build-essential libpq-dev \
  python3 python3-venv python3-dev postgresql nginx snmp iputils-ping rsync openssl
```

El frontend necesita Node.js 22 LTS (Vite requiere Node 20.19+ o 22.12+; consulta [la guía oficial de Vite](https://vite.dev/guide/)):

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node --version
npm --version
```

Consulta [el manual paso a paso para Ubuntu 24.04](docs/manuales/instalacion_servidor_nuevo.md) y [el inventario de licencias de terceros](THIRD_PARTY_NOTICES.md).

## Pasar el proyecto a un servidor nuevo

Sí: puedes instalar el código en otro Ubuntu Server limpio, pero copiar únicamente el directorio del proyecto no traslada automáticamente la instalación ni los datos. La carpeta fuente no contiene por sí sola PostgreSQL, secretos de entorno, certificados TLS, servicios systemd ni los archivos compilados que Nginx publica.

Para una instalación nueva, descarga/clona el código fuente y sigue la sección Instalación limpia. Configura una base PostgreSQL nueva, genera una clave Fernet nueva, instala certificados para el nombre DNS del servidor y crea el primer administrador desde CLI. No copies .env, .venv, logs, PID, certificados ni archivos de respaldo al repositorio ni al paquete de código. No copies la carpeta de producción completa: puede contener configuración y datos privados.

Si lo que buscas es migrar la instancia y conservar usuarios, dispositivos, alertas e historial, eso es una migración de datos: usa el procedimiento documentado en [restauración](docs/manuales/restauracion.md), verifica compatibilidad de la versión del respaldo y conserva la clave que cifra las credenciales guardadas. No mezcles un respaldo de producción con una instalación limpia hasta validar la restauración en un entorno aislado.

## Instalación limpia

Ejecuta los pasos administrativos en un servidor Ubuntu nuevo. Puedes abrir una shell de administrador con sudo -i para las operaciones del sistema; conserva los comandos sudo -u postgres y sudo -u root tal como aparecen.

### 1. Obtener el código

Clona el repositorio público oficial de NetCore NOC: No uses credenciales de producción en esta instalación.

    sudo git clone https://github.com/mrsmith152890/Netcore-noc.git /opt/netcore-noc
    sudo adduser --system --group --no-create-home --home /opt/netcore-noc netcore
    sudo chown -R root:netcore /opt/netcore-noc
    sudo chmod -R g+rX /opt/netcore-noc
    cd /opt/netcore-noc

Si netcore ya existe, no repitas adduser. Conserva la propiedad root:netcore para que los servicios puedan leer el código.

### 2. Preparar PostgreSQL

```bash
sudo systemctl enable --now postgresql
sudo -u postgres createuser --pwprompt netcore
sudo -u postgres createdb --owner=netcore netcore
```

Guarda la contraseña generada en un gestor seguro. Usa una contraseña hexadecimal o codifica los caracteres especiales para que la URL de PostgreSQL sea válida.

### 3. Configurar el backend y sus secretos

```bash
cd /opt/netcore-noc/backend
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
nano .env
```

Configura `.env` con valores propios, por ejemplo:

```dotenv
NOC_ENVIRONMENT=prod
NOC_LOG_LEVEL=INFO
NOC_TIMEZONE=America/Bogota
NOC_DATABASE_URL=postgresql+psycopg://netcore:CAMBIA_ESTA_CLAVE@127.0.0.1:5432/netcore
NOC_SECRET_KEY=PEGA_AQUI_LA_CLAVE_FERNET_GENERADA
NOC_COOKIE_SECURE=true
NOC_TRUST_PROXY=true
NOC_DISCOVERY_ALLOW_PUBLIC=false
```

`NOC_SECRET_KEY` debe ser la clave Fernet generada por el comando anterior. Consérvala fuera del repositorio y respáldala de forma segura: sin ella no se pueden descifrar las credenciales SNMP/Telegram guardadas. `NOC_TRUST_PROXY=true` es apropiado cuando la API solo se expone por Nginx como en esta guía. No publiques `.env` ni compartas volcados de base de datos.

Restringe el archivo y aplica las migraciones:

```bash
sudo chown root:netcore .env
sudo chmod 640 .env
.venv/bin/alembic upgrade head
```

### 4. Crear el primer administrador

```bash
cd /opt/netcore-noc/backend
sudo -u root .venv/bin/python -m app.cli create-user admin --role admin --name 'Administrador NOC'
```

El comando solicita la contraseña sin imprimirla. Usa una contraseña única y guárdala en un gestor seguro. No hay una cuenta inicial ni contraseña por defecto.

### Cambiar o restablecer la contraseña del administrador

El backend ofrece un comando local que pide la nueva contraseña dos veces sin mostrarla:

    cd /opt/netcore-noc/backend
    sudo -u root .venv/bin/python -m app.cli set-password admin

Sustituye admin por el nombre de usuario administrador existente si es distinto. El comando actualiza el hash con el mecanismo seguro de la aplicación, quita el bloqueo por intentos fallidos y revoca las sesiones activas de esa cuenta. Esto cambia la contraseña, no renombra el usuario. Si no recuerdas el nombre, consulta la lista de usuarios desde una sesión administradora o en PostgreSQL con el procedimiento interno de operación; no edites directamente el hash.

### 5. Configurar TLS

Configura un certificado válido para el nombre DNS que usarán los operadores en:

- Certificado: `/etc/ssl/netcore/netcore.crt`
- Llave privada: `/etc/ssl/netcore/netcore.key`

El archivo `deploy/nginx/netcore.conf` referencia esas rutas. Para una instalación de laboratorio puedes crear uno autofirmado (el navegador mostrará una advertencia):

```bash
sudo install -d -m 750 /etc/ssl/netcore
sudo openssl req -x509 -nodes -days 365 -newkey rsa:3072 \
  -keyout /etc/ssl/netcore/netcore.key -out /etc/ssl/netcore/netcore.crt \
  -subj "/CN=noc.example.local" \
  -addext "subjectAltName=DNS:noc.example.local"
sudo chmod 600 /etc/ssl/netcore/netcore.key
sudo chmod 644 /etc/ssl/netcore/netcore.crt
```

Usa el DNS que realmente configuraste y añade su nombre alternativo (`subjectAltName`). Para operación normal usa una CA interna confiable o un certificado válido. Mantén la llave privada fuera del repositorio.

### 6. Instalar los procesos y Nginx

Ejecuta como root desde /opt/netcore-noc:

    cd /opt/netcore-noc
    ./deploy/scripts/generate-units.sh
    ./deploy/scripts/install-services.sh
    ./deploy/scripts/build-frontend.sh
    ./deploy/scripts/install-nginx.sh
    systemctl start netcore.target

install-nginx.sh instala el sitio y sus snippets en sites-available, conf.d y snippets, crea el enlace sites-enabled/netcore, valida con nginx -t y recarga Nginx solo si la validación termina bien. Si hay una configuración netcore diferente, aborta sin sobrescribirla. No elimina ni deshabilita el sitio default ni otras configuraciones. Revisa conflictos de default_server en una instalación Ubuntu limpia antes de habilitar el sitio; la plantilla actual usa default_server para HTTP y HTTPS. Si Nginx rechaza esa combinación, no borres configuraciones automáticamente: identifica el sitio conflictivo y decide manualmente cómo enrutar el nombre DNS.

La plantilla está en deploy/nginx/netcore.conf. Esta versión usa el frontend compilado en /var/www/netcore, escucha en 80/443, redirige HTTP a HTTPS y envía /api/ a 127.0.0.1:8000. Debes tener certificados TLS disponibles en /etc/ssl/netcore/netcore.crt y /etc/ssl/netcore/netcore.key, con permisos de lectura apropiados para Nginx y acceso restringido a la clave privada. netcore-limits.conf declara el límite de solicitudes de login; los snippets proxy y security definen cabeceras y reglas comunes.

Para verificar manualmente:

    sudo nginx -t
    sudo systemctl reload nginx
    curl -I http://NOMBRE_DNS/
    curl -kI https://NOMBRE_DNS/
    curl -i https://NOMBRE_DNS/api/health

Usa -k únicamente para certificados autofirmados de laboratorio. Si falla la instalación, revisa el mensaje y sudo nginx -t; el script revierte solo los archivos que creó en ese intento. Si el reload falla, corrige primero la causa y vuelve a validar. Para desinstalar, retira únicamente /etc/nginx/sites-enabled/netcore si apunta al sitio del proyecto y los archivos netcore administrados por esta aplicación; conserva default, snippets y configuraciones ajenas. No borres certificados o claves sin confirmar que no los usa otro servicio.

Permite en el firewall solo los puertos necesarios (normalmente TCP 443 y, si deseas redirección HTTP, TCP 80). **No expongas los puertos 8000/8001 a la red.** El servicio netcore-api-dev es solo para desarrollo y no forma parte del arranque de producción. No ejecutes npm run dev como servicio de producción.

### 7. Validar el despliegue

```bash
/opt/netcore-noc/deploy/scripts/smoke-test.sh
systemctl --no-pager --failed
systemctl list-timers 'netcore-*'
```

Abre `https://NOMBRE_DNS/`, inicia sesión con el administrador y cambia su contraseña cuando corresponda. La documentación OpenAPI solo se habilita en modo desarrollo; en producción la API no publica `/docs`.

## Integraciones y primera configuración

1. **Dispositivos:** agrega las direcciones IP y asígnalas a sedes. Configura el tipo de dispositivo y los parámetros WAN en routers/firewalls donde aplique.
2. **SNMP:** registra las credenciales desde la interfaz de administración. La comunidad/clave se almacena cifrada con `NOC_SECRET_KEY`; permite UDP 161 entre el servidor y los equipos, y limita su origen al servidor NOC.
3. **Telegram:** en *Alertas*, registra el token del bot y el `chat_id` destino. El backend valida el bot/chat y cifra estos datos en la base de datos. Nunca los escribas en README, logs ni scripts.
4. **Reglas y mantenimiento:** define reglas de alertas y canales; los administradores pueden programar ventanas por sede o dispositivo. Durante una ventana se silencian notificaciones, mientras el estado permanece visible.
5. **Descubrimiento:** registra únicamente los rangos que tienes autorización para consultar. El escaneo se ejecuta bajo demanda. El descubrimiento de rangos públicos está desactivado por defecto; actívalo únicamente para rangos propios autorizados, por ejemplo una red VPN bajo tu control.
6. **Mapas y dominios:** crea mapas, asigna dominios y organiza dispositivos/submapas desde la interfaz. La identidad visual y el resumen del login se administran desde *Identidad visual*.

Abre en el firewall de cada segmento solo los protocolos requeridos: ICMP para ping, UDP 161 para SNMP y los puertos TCP/HTTP/DNS que se hayan configurado como chequeos de servicio.

## Operación y actualizaciones

Los servicios se administran con `systemctl`; sus registros están en el journal:

```bash
systemctl status netcore.target netcore-api nginx postgresql
journalctl -u netcore-api -n 100 --no-pager
journalctl -u netcore-alerts -f
```

Para actualizar el código desde la rama principal, como administrador del servidor:

```bash
cd /opt/netcore-noc
git pull --ff-only origin main
./deploy/scripts/update.sh --frontend
./deploy/scripts/smoke-test.sh
```

El script de actualización instala dependencias del backend, aplica Alembic, compila y reinicia los servicios. Para cambios exclusivos de frontend, el script acepta `--frontend`; la publicación completa recomendada es la mostrada arriba.

## Copias y recuperación

El instalador habilita copias diarias, limpieza de históricos y una prueba semanal de restauración. Las copias se guardan en `/var/backups/netcore`; la clave para cifrar el paquete de secretos se mantiene en `/root/.netcore-backup-pass` y debe respaldarse por separado, fuera del servidor. La réplica SSH es opcional y se configura en `/etc/netcore-backup.conf`, fuera del repositorio.

Consulta el procedimiento detallado en [docs/manuales/restauracion.md](docs/manuales/restauracion.md) y las tareas de operación en [docs/manuales/operacion.md](docs/manuales/operacion.md).

## Desarrollo local

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # completa primero DB y clave Fernet
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

En otra terminal:

```bash
cd frontend
npm ci
npm run dev -- --config vite.dev.config.ts --host 0.0.0.0
```

La API de desarrollo requiere `NOC_ENVIRONMENT=dev` y `NOC_COOKIE_SECURE=false` si se accede sin HTTPS. No reutilices la base de datos/credenciales de desarrollo en producción. Para producción usa los servicios systemd y el frontend compilado.

## Estructura del repositorio

```text
backend/       API, modelos, workers y migraciones
frontend/      interfaz React/TypeScript
deploy/        Nginx, systemd y scripts de instalación/operación
 docs/         arquitectura y manuales de operación/restauración
```

## Seguridad del repositorio

La carpeta de una instalación productiva puede contener configuración local y archivos que no deben distribuirse. Antes de publicar, prepara un paquete de código limpio y verifica que no incluya .env, .venv, datos de PostgreSQL, llaves TLS, claves Fernet, tokens de Telegram, comunidades SNMP, volcados, logs, PID ni archivos de respaldo. Si un secreto se añadió alguna vez al historial Git, quitar el archivo actual no lo elimina del historial: rótalo y revisa el historial antes de publicar. Mantén los secretos separados por instalación.


## Estado de publicación\n\nConsulta [el estado y los pasos pendientes antes de publicar](docs/PUBLICACION.md).\n\n## Licencia

El código propio de NetCore NOC Manager se ofrece bajo GNU GPL-3.0-only; el texto completo está en [LICENSE](LICENSE). Las dependencias, imágenes, fuentes y otros recursos de terceros pueden tener términos distintos y deben conservar sus avisos. La licencia del proyecto no reemplaza la revisión de procedencia ni concede derechos sobre componentes de terceros.
