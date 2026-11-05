from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()
_DUMMY = _ph.hash("contraseña-ficticia-para-igualar-tiempos")

def hash_password(password: str) -> str:
    return _ph.hash(password)

def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False

def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)

def burn_time(password: str) -> None:
    """Verifica contra un hash ficticio para que 'usuario inexistente' tarde lo mismo que 'clave incorrecta'."""
    verify_password(_DUMMY, password)
