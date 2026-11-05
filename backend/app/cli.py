"""Administración local: python -m app.cli create-user NOMBRE --role admin"""
import argparse
import getpass
import re
import sys

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.core.passwords import hash_password
from app.models import User, UserSession

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")

def _ask_password() -> str:
    while True:
        p1 = getpass.getpass("Contraseña (mínimo 10 caracteres): ")
        if len(p1) < 10:
            print("Es demasiado corta.")
            continue
        if p1 != getpass.getpass("Repite la contraseña: "):
            print("No coinciden.")
            continue
        return p1

def create_user(args) -> None:
    username = args.username.strip().lower()
    if not USERNAME_RE.match(username):
        sys.exit("Usuario inválido (3-32 caracteres: letras, números, punto, guion, guion bajo)")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            sys.exit("Ese usuario ya existe")
        db.add(User(username=username, full_name=args.name, role=args.role,
                    password_hash=hash_password(_ask_password()), enabled=True))
        db.commit()
    print(f"Usuario «{username}» creado con rol {args.role}.")

def set_password(args) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username.strip().lower()))
        if not user:
            sys.exit("Usuario no encontrado")
        user.password_hash = hash_password(_ask_password())
        user.failed_logins, user.locked_until, user.must_change_password = 0, None, False
        db.execute(update(UserSession).where(UserSession.user_id == user.id).values(revoked=True))
        db.commit()
    print("Contraseña actualizada, cuenta desbloqueada y sesiones cerradas.")

def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user", help="crear un usuario")
    c.add_argument("username")
    c.add_argument("--role", choices=["viewer", "operator", "admin"], default="admin")
    c.add_argument("--name", default=None, help="nombre completo")
    c.set_defaults(func=create_user)
    p = sub.add_parser("set-password", help="restablecer contraseña y desbloquear")
    p.add_argument("username")
    p.set_defaults(func=set_password)
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
