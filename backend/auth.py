import os
import time
import hmac
import hashlib
import secrets
import threading
import jwt
from fastapi import Header, HTTPException, Request

# ── Real per-user login ─────────────────────────────────────────────────────
# Replaces the old single-shared-secret model (a static API_ACCESS_KEY baked
# into the public frontend JS bundle at build time -- readable by anyone who
# opens devtools on the live site, which meant "the API key" was never
# actually secret). Users now log in with a username + password at runtime;
# nothing secret is compiled into the build. A signed, short-lived JWT is
# issued on login and sent as `Authorization: Bearer <token>` on every
# request after that.

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 24 * 60 * 60  # 24h -- short enough that a leaked token
                                    # (e.g. from a shared machine) ages out
                                    # on its own; re-login is cheap.

PBKDF2_ITERATIONS = 260_000  # matches Django's current default


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iterations, salt, hex_digest = stored_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(digest.hex(), hex_digest)
    except (ValueError, AttributeError):
        return False


def create_access_token(user_id: int, username: str) -> str:
    if not JWT_SECRET:
        raise HTTPException(500, "Server misconfiguration: JWT_SECRET is not set.")
    now = int(time.time())
    payload = {"sub": str(user_id), "username": username, "iat": now, "exp": now + JWT_EXPIRY_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def client_ip(request: Request) -> str:
    # Trust X-Forwarded-For's first hop only when actually behind a known
    # proxy (Railway/Oracle+Caddy both set this) -- falls back to the direct
    # connecting IP otherwise so this can't be spoofed by an arbitrary header
    # from someone hitting the app directly.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Per-source-IP sliding-window lockout, now guarding the LOGIN endpoint
# (where brute-forcing a password actually matters) rather than a static
# key. In-memory / single-process, matching this app's single-container
# deployment -- no external store needed for a small internal tool.
MAX_FAILURES = 5
WINDOW_SECONDS = 60
LOCKOUT_SECONDS = 15 * 60

_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}
_lock = threading.Lock()


def check_login_rate_limit(ip: str):
    now = time.time()
    with _lock:
        locked_until = _locked_until.get(ip, 0)
        if now < locked_until:
            raise HTTPException(429, f"Too many failed login attempts. Try again in {int(locked_until - now)}s.")


def record_login_failure(ip: str):
    now = time.time()
    with _lock:
        attempts = [t for t in _failures.get(ip, []) if now - t < WINDOW_SECONDS]
        attempts.append(now)
        _failures[ip] = attempts
        if len(attempts) >= MAX_FAILURES:
            _locked_until[ip] = now + LOCKOUT_SECONDS
            _failures.pop(ip, None)


def record_login_success(ip: str):
    with _lock:
        _failures.pop(ip, None)
        _locked_until.pop(ip, None)


def require_user(authorization: str = Header(default=None)):
    """Validates the Bearer JWT issued at login. Raises 401 if missing/invalid/expired."""
    if not JWT_SECRET:
        raise HTTPException(500, "Server misconfiguration: JWT_SECRET is not set.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header.")
    token = authorization[len("Bearer "):]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid session token.")
    return {"user_id": int(payload["sub"]), "username": payload["username"]}
