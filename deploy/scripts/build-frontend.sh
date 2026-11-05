#!/usr/bin/env bash
# Compila el frontend y lo publica en /var/www/netcore (lo sirve nginx).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/frontend"
npm ci --no-audit --no-fund
npm run build
install -d -m 755 /var/www/netcore
rsync -a --delete dist/ /var/www/netcore/
echo "Frontend publicado en /var/www/netcore"
