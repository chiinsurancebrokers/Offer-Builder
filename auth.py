"""auth.py — single-user login stored in Supabase.

The password hash never leaves the database: the app calls two RPC functions
(ob_login, ob_change_password) with the publishable key. The table itself has
RLS on and no policies, so the key alone cannot read it. Lockout (5 wrong
attempts -> 15 minutes) is enforced inside the database.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class AuthUnavailable(Exception):
    pass


def _call(fn: str, payload: dict) -> dict:
    url = os.environ.get("SUPABASE_URL", "").strip().strip("\"'").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "").strip().strip("\"'")
    if not url or not key:
        raise AuthUnavailable("Λείπουν τα SUPABASE_URL / SUPABASE_KEY.")
    req = urllib.request.Request(
        f"{url}/rest/v1/rpc/{fn}", data=json.dumps(payload).encode(), method="POST",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise AuthUnavailable(f"Supabase HTTP {e.code}") from e
    except Exception as e:  # network, DNS, timeout
        raise AuthUnavailable(f"Supabase: {type(e).__name__}") from e


def login(password: str) -> dict:
    return _call("ob_login", {"p_password": password})


def change_password(old: str, new: str) -> dict:
    return _call("ob_change_password", {"p_old": old, "p_new": new})
