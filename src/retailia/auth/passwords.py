"""Password hashing with the standard library's scrypt (memory-hard, salted).

Stored format: ``scrypt:<log2 n>:<r>:<p>:<salt b64>:<digest b64>``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

LOG2_N, BLOCK_SIZE, PARALLELISM, DIGEST_BYTES = 14, 8, 1, 32
MIN_PASSWORD_LENGTH = 8


class WeakPassword(ValueError):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, log2_n: int, r: int, p: int, size: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=1 << log2_n, r=r, p=p, dklen=size,
                          maxmem=256 * 1024 * 1024)


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(f"passwords need at least {MIN_PASSWORD_LENGTH} characters")
    salt = os.urandom(16)
    digest = _derive(password, salt, LOG2_N, BLOCK_SIZE, PARALLELISM, DIGEST_BYTES)
    return ":".join(["scrypt", str(LOG2_N), str(BLOCK_SIZE), str(PARALLELISM), _b64(salt), _b64(digest)])


def check_password(password: str, stored: str) -> bool:
    parts = stored.split(":")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        log2_n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt, expected = base64.b64decode(parts[4]), base64.b64decode(parts[5])
        actual = _derive(password, salt, log2_n, r, p, len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Verified against when the username does not exist, so response time does not reveal valid usernames.
DUMMY_HASH = "scrypt:14:8:1:AAAAAAAAAAAAAAAAAAAAAA==:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
