"""Mantenimiento: python -m app.maintenance [--dry-run]"""
import argparse
import logging

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from app.modules.maintenance.retention import purge

def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.maintenance")
    parser.add_argument("--dry-run", action="store_true", help="solo cuenta lo que se borraría")
    args = parser.parse_args()
    setup_logging()
    result = purge(SessionLocal, dry_run=args.dry_run)
    verb = "a borrar" if args.dry_run else "borradas"
    for name, n in result.items():
        print(f"{name:20s} {n:>10d} filas {verb}")
    logging.getLogger("netcore.maintenance").info(
        "Retención %s: %s", "simulada" if args.dry_run else "aplicada", result)

if __name__ == "__main__":
    main()
