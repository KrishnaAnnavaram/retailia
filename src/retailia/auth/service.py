"""Login with lockout, and server-side sessions holding a typed :class:`Principal`."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from retailia.auth.passwords import DUMMY_HASH, check_password
from retailia.data.db import StoreDB

Clock = Callable[[], datetime]
TIME_FMT = "%Y-%m-%dT%H:%M:%S"


class LoginFailed(Exception):
    """Wrong username/password or a locked account. The message never says which."""


@dataclass(frozen=True)
class Principal:
    """Who is signed in. ``customer_id`` is a plain int taken from the database row."""

    customer_id: int
    username: str
    role: str  # "customer" | "staff"
    email: str

    @property
    def is_staff(self) -> bool:
        return self.role == "staff"


class AuthService:
    def __init__(self, db: StoreDB, clock: Clock = datetime.now, *, max_failures: int = 5,
                 lockout_minutes: int = 15) -> None:
        self.db = db
        self.clock = clock
        self.max_failures = max_failures
        self.lockout = timedelta(minutes=lockout_minutes)

    def login(self, username: str, password: str) -> Principal:
        username = username.strip().lower()
        now = self.clock()
        ok = False
        with self.db.read_write() as conn:  # commits the counter update even when the login fails
            row = conn.execute(
                "SELECT customer_id, username, password_hash, role, email, failed_logins, locked_until "
                "FROM customers WHERE username = ?", (username,),
            ).fetchone()
            if row is None:
                check_password(password, DUMMY_HASH)  # equalise timing
            elif row["locked_until"] and datetime.strptime(row["locked_until"], TIME_FMT) > now:
                pass  # locked: do not even check the password
            elif check_password(password, row["password_hash"]):
                ok = True
                conn.execute("UPDATE customers SET failed_logins = 0, locked_until = NULL WHERE customer_id = ?",
                             (row["customer_id"],))
            else:
                failures = row["failed_logins"] + 1
                locked = (now + self.lockout).strftime(TIME_FMT) if failures >= self.max_failures else None
                conn.execute("UPDATE customers SET failed_logins = ?, locked_until = ? WHERE customer_id = ?",
                             (0 if locked else failures, locked, row["customer_id"]))
        if not ok:
            raise LoginFailed("invalid username or password")
        return Principal(int(row["customer_id"]), row["username"], row["role"], row["email"])


@dataclass
class _SessionRecord:
    principal: Principal
    expires_at: datetime


class SessionStore:
    """In-memory, server-side sessions with idle expiry. The browser only ever holds an opaque token."""

    def __init__(self, ttl_minutes: int = 30, clock: Clock = datetime.now) -> None:
        self.ttl = timedelta(minutes=ttl_minutes)
        self.clock = clock
        self._sessions: dict[str, _SessionRecord] = {}

    def create(self, principal: Principal) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = _SessionRecord(principal, self.clock() + self.ttl)
        return token

    def get(self, token: str | None) -> Principal | None:
        record = self._sessions.get(token or "")
        if record is None:
            return None
        if record.expires_at <= self.clock():
            self._sessions.pop(token, None)
            return None
        record.expires_at = self.clock() + self.ttl  # sliding expiry
        return record.principal

    def revoke(self, token: str) -> None:
        self._sessions.pop(token, None)
