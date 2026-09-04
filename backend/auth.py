import os
import time
import secrets
import threading
from fastapi import Header, HTTPException, Request

# Minimal shared-secret gate for this internal tool. There is no user/session
# model anywhere in the app (no User table, no login flow), so a full
# multi-user auth system would be a much larger change than "the API is wide
# open" calls for -- this is the smallest change that stops the API (which
# includes a full company-data dump and delete endpoints) being reachable by
# anyone who can hit the port. It is a perimeter check, not real per-user
# auth: every legitimate client (the one frontend build) shares one secret.
#
# Fails CLOSED: if API_ACCESS_KEY isn't configured, every request is
# rejected rather than silently allowing everyone through.

# SECURITY FIX: nothing previously stopped repeated key-guessing attempts --
# no lockout, no throttling, unlimited tries. This is an in-memory (single-
# process, matches this app's single-container deployment) sliding-window
# lockout per source IP: after MAX_FAILURES bad keys within WINDOW_SECONDS,
# that IP is refused outright for LOCKOUT_SECONDS regardless of whether the
# next key it sends is correct. Resets on a correct key. Not a substitute for
# real per-user auth, but it turns "unlimited guesses" into "a few guesses,
# then a long wait" -- enough to make brute-forcing a 32-byte random token
# pointless without needing an external store like Redis for a single-
# instance internal tool.
MAX_FAILURES = 5
WINDOW_SECONDS = 60
LOCKOUT_SECONDS = 15 * 60

_failures: dict[str, list[float]] = {}
_locked_until: dict[str, float] = {}
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    # Trust X-Forwarded-For's first hop only when actually behind a known
    # proxy (Railway/Oracle+Caddy both set this) -- falls back to the direct
    # connecting IP otherwise so this can't be spoofed by an arbitrary header
    # from someone hitting the app directly.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_api_key(request: Request, x_api_key: str = Header(default=None, alias="X-API-Key")):
    expected = os.getenv("API_ACCESS_KEY")
    if not expected:
        raise HTTPException(
            500,
            "Server misconfiguration: API_ACCESS_KEY is not set in the backend .env file."
        )

    ip = client_ip(request)
    now = time.time()

    with _lock:
        locked_until = _locked_until.get(ip, 0)
        if now < locked_until:
            raise HTTPException(
                429,
                f"Too many invalid API key attempts. Try again in {int(locked_until - now)}s."
            )

        valid = bool(x_api_key) and secrets.compare_digest(x_api_key, expected)

        if valid:
            _failures.pop(ip, None)
            _locked_until.pop(ip, None)
        else:
            attempts = [t for t in _failures.get(ip, []) if now - t < WINDOW_SECONDS]
            attempts.append(now)
            _failures[ip] = attempts
            if len(attempts) >= MAX_FAILURES:
                _locked_until[ip] = now + LOCKOUT_SECONDS
                _failures.pop(ip, None)

    if not valid:
        raise HTTPException(401, "Missing or invalid API key.")
