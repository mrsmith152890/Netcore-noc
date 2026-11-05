#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd -P)"
SOURCE_DIR="$PROJECT_DIR/deploy/nginx"

NGINX_ETC_DIR="${NGINX_ETC_DIR:-/etc/nginx}"
NGINX_CONF_DIR="${NGINX_CONF_DIR:-$NGINX_ETC_DIR/conf.d}"
NGINX_SNIPPETS_DIR="${NGINX_SNIPPETS_DIR:-$NGINX_ETC_DIR/snippets}"
NGINX_SITES_AVAILABLE_DIR="${NGINX_SITES_AVAILABLE_DIR:-$NGINX_ETC_DIR/sites-available}"
NGINX_SITES_ENABLED_DIR="${NGINX_SITES_ENABLED_DIR:-$NGINX_ETC_DIR/sites-enabled}"
NGINX_BIN="${NGINX_BIN:-nginx}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"

created_files=()
created_link=""

rollback_created() {
    local path
    for path in "${created_files[@]}"; do
        rm -f -- "$path"
    done
    if [[ -n "$created_link" ]]; then
        rm -f -- "$created_link"
    fi
}

on_exit() {
    local status=$?
    if (( status != 0 )); then
        rollback_created
        echo "ERROR: instalación Nginx fallida (código $status); se revirtieron únicamente los archivos creados por este intento." >&2
    fi
}
trap on_exit EXIT

die() {
    echo "ERROR: $*" >&2
    exit 1
}

for command_name in install cmp "$NGINX_BIN" "$SYSTEMCTL_BIN"; do
    command -v "$command_name" >/dev/null 2>&1 || die "No se encontró el comando requerido: $command_name"
done

for source in netcore-limits.conf netcore-proxy.conf netcore-security.conf netcore.conf; do
    [[ -f "$SOURCE_DIR/$source" ]] || die "Falta el archivo fuente $SOURCE_DIR/$source"
done

install -d -m 755 "$NGINX_CONF_DIR" "$NGINX_SNIPPETS_DIR" "$NGINX_SITES_AVAILABLE_DIR" "$NGINX_SITES_ENABLED_DIR"

install_if_absent_or_identical() {
    local source="$1" target="$2"
    if [[ -e "$target" || -L "$target" ]]; then
        [[ -f "$target" && ! -L "$target" ]] || die "Conflicto: $target existe y no es un archivo regular administrable"
        cmp -s -- "$source" "$target" || die "Conflicto: $target ya existe con contenido diferente; no se sobrescribió"
        echo "Sin cambios (idéntico): $target"
        return
    fi
    install -m 644 -- "$source" "$target"
    created_files+=("$target")
    echo "Instalado: $target"
}

site_file="$NGINX_SITES_AVAILABLE_DIR/netcore"
site_link="$NGINX_SITES_ENABLED_DIR/netcore"
install_if_absent_or_identical "$SOURCE_DIR/netcore-limits.conf" "$NGINX_CONF_DIR/netcore-limits.conf"
install_if_absent_or_identical "$SOURCE_DIR/netcore-proxy.conf" "$NGINX_SNIPPETS_DIR/netcore-proxy.conf"
install_if_absent_or_identical "$SOURCE_DIR/netcore-security.conf" "$NGINX_SNIPPETS_DIR/netcore-security.conf"
install_if_absent_or_identical "$SOURCE_DIR/netcore.conf" "$site_file"

if [[ -L "$site_link" ]]; then
    [[ "$(readlink -- "$site_link")" == "$site_file" ]] || die "Conflicto: $site_link apunta a otro destino; no se modificó"
elif [[ -e "$site_link" ]]; then
    die "Conflicto: $site_link existe y no es el enlace esperado; no se modificó"
else
    ln -s -- "$site_file" "$site_link"
    created_link="$site_link"
    echo "Activado: $site_link"
fi

"$NGINX_BIN" -t
"$SYSTEMCTL_BIN" reload nginx
echo "Nginx quedó configurado, validado y recargado correctamente."
