from app.core.passwords import hash_password, needs_rehash, verify_password

def test_roundtrip():
    h = hash_password("una-clave-larga-123")
    assert verify_password(h, "una-clave-larga-123")

def test_wrong_password_fails():
    assert not verify_password(hash_password("una-clave-larga-123"), "otra-clave-larga")

def test_hashes_are_salted():
    assert hash_password("misma-clave-123") != hash_password("misma-clave-123")

def test_garbage_hash_is_rejected():
    assert not verify_password("esto-no-es-un-hash", "algo")

def test_fresh_hash_does_not_need_rehash():
    assert not needs_rehash(hash_password("una-clave-larga-123"))
