"""Admin authentication: scrypt password hashes, in-memory sessions, login throttling."""
import base64
import hashlib
import hmac
import secrets
import threading
import time
from typing import Optional, Tuple

SESSION_TTL = 12 * 3600
MAX_FAILURES = 5
LOCKOUT = 300  # seconds
MIN_PASSWORD_LEN = 10

_SCRYPT = dict(n=2 ** 14, r=8, p=1)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    b64 = lambda b: base64.b64encode(b).decode()
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${b64(salt)}${b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(dk)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                             n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(got, expected)
    except (ValueError, TypeError):
        return False


class SessionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions = {}   # token -> (expires, csrf)
        self._failures = {}   # ip -> (count, locked_until)

    def create(self) -> Tuple[str, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self._lock:
            now = time.time()
            self._sessions = {k: v for k, v in self._sessions.items() if v[0] > now}
            self._sessions[token] = (now + SESSION_TTL, csrf)
        return token, csrf

    def get(self, token: Optional[str]) -> Optional[str]:
        """Return the CSRF token of a valid session, else None."""
        if not token:
            return None
        with self._lock:
            entry = self._sessions.get(token)
            if not entry or entry[0] < time.time():
                self._sessions.pop(token, None)
                return None
            return entry[1]

    def destroy(self, token: Optional[str]) -> None:
        with self._lock:
            self._sessions.pop(token, None)

    def destroy_all(self) -> None:
        with self._lock:
            self._sessions.clear()

    # --- brute force protection ---
    def locked_for(self, ip: str) -> int:
        with self._lock:
            _, until = self._failures.get(ip, (0, 0))
            return max(0, int(until - time.time()))

    def record_failure(self, ip: str) -> None:
        with self._lock:
            count, _ = self._failures.get(ip, (0, 0))
            count += 1
            until = time.time() + LOCKOUT if count >= MAX_FAILURES else 0
            self._failures[ip] = (0 if until else count, until)

    def record_success(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)
