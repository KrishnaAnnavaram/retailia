"""Problems 3 and 4: hashed passwords, one unified schema, integer customer ids."""

from datetime import timedelta

import pytest

from retailia.auth.passwords import WeakPassword, check_password, hash_password
from retailia.auth.service import AuthService, LoginFailed, SessionStore
from retailia.data.repositories import CustomerScope
from tests.conftest import PASSWORD, Clock


def test_hash_is_salted_and_verifiable():
    a, b = hash_password("correct horse"), hash_password("correct horse")
    assert a != b and a.startswith("scrypt:") and "correct horse" not in a
    assert check_password("correct horse", a)
    assert not check_password("correct horsE", a)
    assert not check_password("anything", "plaintext-password")
    with pytest.raises(WeakPassword):
        hash_password("short")


def test_no_plaintext_passwords_in_database(db):
    with db.read_only() as conn:
        hashes = [r[0] for r in conn.execute("SELECT password_hash FROM customers")]
    assert hashes and all(h.startswith("scrypt:") for h in hashes)
    assert all(PASSWORD not in h for h in hashes)


def test_login_returns_integer_customer_id_from_unified_table(app, db):
    principal = app.auth.login("Customer02 ", PASSWORD)
    assert type(principal.customer_id) is int and principal.role == "customer"
    with db.read_only() as conn:
        row = conn.execute("SELECT customer_id FROM customers WHERE username = 'customer02'").fetchone()
    assert principal.customer_id == row[0]


def test_scope_rejects_tuple_ids(db):
    with pytest.raises(TypeError):
        CustomerScope(db, (2,))


def test_wrong_password_and_unknown_user_look_the_same(app):
    with pytest.raises(LoginFailed) as wrong:
        app.auth.login("customer02", "not-the-password")
    with pytest.raises(LoginFailed) as unknown:
        app.auth.login("nobody", "not-the-password")
    assert str(wrong.value) == str(unknown.value)


def test_lockout_after_repeated_failures(db):
    clock = Clock()
    auth = AuthService(db, clock, max_failures=3, lockout_minutes=10)
    for _ in range(3):
        with pytest.raises(LoginFailed):
            auth.login("customer03", "wrong-password")
    with pytest.raises(LoginFailed):
        auth.login("customer03", PASSWORD)  # locked even with the right password
    clock.now += timedelta(minutes=11)
    assert auth.login("customer03", PASSWORD).username == "customer03"


def test_sessions_expire_and_revoke(app, customer):
    clock = Clock()
    store = SessionStore(ttl_minutes=5, clock=clock)
    token = store.create(customer)
    assert store.get(token) == customer and store.get("forged-token") is None
    clock.now += timedelta(minutes=6)
    assert store.get(token) is None
    token = store.create(customer)
    store.revoke(token)
    assert store.get(token) is None
