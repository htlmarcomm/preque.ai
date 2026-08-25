import os
import secrets
from fastapi import Header, HTTPException

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


def require_api_key(x_api_key: str = Header(default=None, alias="X-API-Key")):
    expected = os.getenv("API_ACCESS_KEY")
    if not expected:
        raise HTTPException(
            500,
            "Server misconfiguration: API_ACCESS_KEY is not set in the backend .env file."
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401, "Missing or invalid API key.")
