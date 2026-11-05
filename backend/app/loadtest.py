"""Datos sintéticos para pruebas de carga.
   python -m app.loadtest create --devices 300 [--dead 100] [--snmp] [--services]
   python -m app.loadtest clean"""
import argparse
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.core.security import encrypt
from app.models import Device, ServiceCheck, Silence, Site, SnmpCredential

SITE = "LOADTEST"

def ip_alive(i: int) -> str:
    return f"127.10.{i // 250}.{1 + i % 250}"

def ip_dead(i: int) -> str:
    return f"127.20.{i // 250}.{1 + i % 250}"

DEV = "(select id from devices where site_id = :s)"
CLEAN = [
    f"delete from interface_samples where interface_id in (select id from interfaces where device_id in {DEV})",
    f"delete from interfaces where device_id in {DEV}",
    f"delete from ping_samples where device_id in {DEV}",
    f"delete from status_events where device_id in {DEV}",
    f"delete from device_status where device_id in {DEV}",
    f"delete from device_metrics where device_id in {DEV}",
    f"delete from snmp_credentials where device_id in {DEV}",
    f"delete from snmp_identity where device_id in {DEV}",
    f"delete from notifications where alert_id in (select id from alerts where device_id in {DEV})",
    f"delete from alerts where device_id in {DEV}",
    f"delete from alert_silences where device_id in {DEV} or site_id = :s",
    f"delete from map_nodes where device_id in {DEV}",
    f"delete from service_checks where device_id in {DEV}",
    f"update discovered_hosts set device_id = null where device_id in {DEV}",
    "delete from devices where site_id = :s",
    "delete from sites where id = :s",
]

def create(args) -> None:
    with SessionLocal() as db:
        if db.scalar(select(Site).where(Site.name == SITE)):
            sys.exit("Ya existe la sede LOADTEST: ejecuta primero 'clean'")
        site = Site(name=SITE, description="Datos sintéticos de prueba de carga")
        db.add(site)
        db.flush()
        alive = [Device(site_id=site.id, name=f"lt-{i:04d}", ip_address=ip_alive(i), device_type="server")
                 for i in range(args.devices)]
        dead = [Device(site_id=site.id, name=f"lt-dead-{i:04d}", ip_address=ip_dead(i), device_type="server")
                for i in range(args.dead)]
        db.add_all(alive + dead)
        db.flush()
        enc = encrypt(args.community)
        for d in alive:
            if args.snmp:
                db.add(SnmpCredential(device_id=d.id, version="2c", port=161, community_enc=enc, enabled=True))
            if args.services:
                db.add(ServiceCheck(device_id=d.id, name="SSH", kind="tcp", port=22, interval_s=60,
                                    timeout_s=5, fail_threshold=3, enabled=True))
        now = datetime.now(timezone.utc)
        db.add(Silence(site_id=site.id, starts_at=now, ends_at=now + timedelta(hours=args.silence_hours),
                       reason="Prueba de carga"))
        db.commit()
    print(f"Creados {args.devices} dispositivos vivos y {args.dead} caídos (silenciados {args.silence_hours} h).")
    if args.dead:
        print("Para simular la caída: iptables -A OUTPUT -d 127.20.0.0/16 -p icmp -j DROP")

def clean(_args) -> None:
    with SessionLocal() as db:
        site = db.scalar(select(Site).where(Site.name == SITE))
        if not site:
            sys.exit("No hay datos de prueba de carga")
        for stmt in CLEAN:
            db.execute(text(stmt), {"s": site.id})
        db.commit()
    print("Datos de prueba eliminados. Ejecuta: runuser -u postgres -- vacuumdb -z netcore")

def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.loadtest")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--devices", type=int, default=300)
    c.add_argument("--dead", type=int, default=0)
    c.add_argument("--snmp", action="store_true")
    c.add_argument("--services", action="store_true")
    c.add_argument("--community", default="noc")
    c.add_argument("--silence-hours", type=int, default=3)
    c.set_defaults(func=create)
    sub.add_parser("clean").set_defaults(func=clean)
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
