#!/usr/bin/env bash
# Aplica cambios: dependencias, migraciones, (opcional) frontend, y reinicia el backend.
# Uso: ./update.sh [--frontend]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT/backend"
source .venv/bin/activate
pip install -q -r requirements.txt
alembic upgrade head
python -m compileall -q app > /dev/null
if [ "${1:-}" = "--frontend" ]; then "$ROOT/deploy/scripts/build-frontend.sh"; fi
systemctl restart netcore.target
systemctl --no-pager --failed
