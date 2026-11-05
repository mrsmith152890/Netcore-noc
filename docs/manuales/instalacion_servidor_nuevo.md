# Instalación limpia en Ubuntu Server 24.04

Este procedimiento crea una instancia vacía. No restaura usuarios, dispositivos, configuración, certificados ni datos del servidor anterior. Debe validarse en una VM limpia antes de producción.

## 1. Preparar Ubuntu

Actualiza el sistema e instala herramientas requeridas:

    sudo apt update
    sudo apt install -y git curl ca-certificates build-essential libpq-dev python3 python3-venv python3-dev postgresql nginx snmp iputils-ping rsync openssl

Instala Node.js 22 LTS desde el repositorio oficial de NodeSource y comprueba las versiones:

    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt install -y nodejs
    node --version
    npm --version

Revisa la procedencia del script desde https://github.com/nodesource/distributions antes de ejecutarlo.

## 2. Obtener código limpio

Reemplaza el URL de ejemplo por el repositorio oficial cuando esté publicado:

    sudo git clone https://github.com/OWNER/REPOSITORY.git /opt/netcore-noc
    sudo adduser --system --group --no-create-home --home /opt/netcore-noc netcore
    sudo chown -R root:netcore /opt/netcore-noc
    sudo chmod -R g+rX /opt/netcore-noc

No copies /opt/netcore-noc del servidor actual. No copies su .env, .venv, PostgreSQL, respaldos, logs, PID, llaves ni certificados. Genera la configuración para este servidor.

## 3. Crear PostgreSQL vacío

    sudo systemctl enable --now postgresql
    sudo -u postgres createuser --pwprompt netcore
    sudo -u postgres createdb --owner=netcore netcore

Guarda la contraseña en un gestor seguro. Codifica los caracteres especiales de la URL de PostgreSQL o elige una contraseña hexadecimal larga para evitar errores de URL.

## 4. Preparar backend y configuración

    cd /opt/netcore-noc/backend
    sudo python3 -m venv .venv
    sudo .venv/bin/pip install --upgrade pip
    sudo .venv/bin/pip install -r requirements.txt
    sudo cp .env.example .env
    sudo .venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'

Edita backend/.env: configura la URL de PostgreSQL y pega una clave Fernet recién generada. No reutilices la clave del servidor anterior. Detrás de Nginx, configura prod, cookie secure y trusted proxy según .env.example; deja el descubrimiento de rangos públicos desactivado salvo que tu operación requiera lo contrario.

    sudo chown root:netcore .env
    sudo chmod 640 .env
    sudo .venv/bin/alembic upgrade head

La clave Fernet protege credenciales SNMP/Telegram almacenadas por la aplicación. Guárdala en un gestor seguro y no la publiques.

## 5. TLS y Nginx

Instala un certificado válido para el nombre DNS de los operadores:

- Certificado: /etc/ssl/netcore/netcore.crt
- Clave privada: /etc/ssl/netcore/netcore.key

Asegura que Nginx pueda leer el certificado y limita el acceso a la clave privada. La plantilla sirve el frontend desde /var/www/netcore y proxy /api/ a 127.0.0.1:8000.

En Ubuntu limpio puede existir el sitio de bienvenida. Solo si verificas que es el enlace predeterminado de Ubuntu, desactiva ese enlace para no tener dos default_server:

    if [ -L /etc/nginx/sites-enabled/default ] && [ "$(readlink -f /etc/nginx/sites-enabled/default)" = "/etc/nginx/sites-available/default" ]; then
      sudo unlink /etc/nginx/sites-enabled/default
    fi

No elimines configuraciones de otros sitios. Como root:

    cd /opt/netcore-noc
    sudo ./deploy/scripts/install-nginx.sh
    sudo nginx -t

El instalador aborta si encuentra archivos netcore diferentes y recarga Nginx solo luego de validar. Si falla, revisa nginx -t y conserva configuraciones ajenas.

## 6. Crear administrador y activar servicios

No existe contraseña predeterminada. El comando solicita la contraseña dos veces sin imprimirla:

    cd /opt/netcore-noc/backend
    sudo -u root .venv/bin/python -m app.cli create-user admin --role admin --name 'Administrador NOC'

Genera e instala unidades, compila el frontend y activa los servicios:

    cd /opt/netcore-noc
    sudo ./deploy/scripts/generate-units.sh /opt/netcore-noc
    sudo ./deploy/scripts/install-services.sh
    sudo ./deploy/scripts/build-frontend.sh
    sudo systemctl start netcore.target

netcore-api-dev es solo desarrollo y no debe habilitarse en producción. No expongas los puertos 8000/8001 directamente.

## 7. Verificar

    sudo nginx -t
    sudo systemctl --no-pager --failed
    sudo systemctl status netcore.target netcore-api nginx postgresql
    sudo /opt/netcore-noc/deploy/scripts/smoke-test.sh

Abre https://NOMBRE_DNS/, inicia sesión y agrega sedes y dispositivos. Abre solo los puertos y protocolos que la monitorización necesite.

## 8. Cambiar la contraseña del administrador

    cd /opt/netcore-noc/backend
    sudo -u root .venv/bin/python -m app.cli set-password admin

Reemplaza admin por el nombre de usuario existente. El comando vuelve a calcular el hash, desbloquea la cuenta y revoca sus sesiones. Cambia la contraseña, no el nombre de usuario.

## Instancia nueva frente a migración

Este procedimiento instala una base vacía. Para conservar usuarios, equipos e historial se necesita una migración separada con respaldos, compatibilidad de versión y la clave Fernet correspondiente. Valida la restauración aisladamente antes de usar datos anteriores.
