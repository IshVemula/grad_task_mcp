"""Reads and writes your Marginalia workspace in Supabase, as you.

It signs in with your site email and password (the same account you use on the website),
so your database's row-level security still applies: this code can only touch your own row.
It never uses the admin "service_role" key.

Saves are versioned. The website and this server can both write, so every save says
"only if the version is still the one I read". If the website saved in the meantime, this
re-reads the newest data and applies the change again, so neither side overwrites the other.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 5


class WorkspaceError(Exception):
    """Something went wrong talking to Supabase; the message says what to do about it."""


class WorkspaceClient:
    def __init__(self, url: str, anon_key: str, email: str, password: str):
        missing = [name for name, value in (("SUPABASE_URL", url), ("SUPABASE_ANON_KEY", anon_key),
                                            ("SUPABASE_EMAIL", email), ("SUPABASE_PASSWORD", password)) if not value]
        if missing:
            raise WorkspaceError(
                "Missing settings in the MCP server's .env file: " + ", ".join(missing) +
                ". Add them (see .env.example) and restart Claude."
            )
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.email = email
        self.password = password
        self._token: str | None = None
        self._refresh: str | None = None
        self._expires_at = 0.0
        self._user_id: str | None = None

    # ------------------------------------------------------------------ http

    def _request(self, method: str, path: str, *, body: Any = None, token: str | None = None,
                 headers: dict[str, str] | None = None) -> tuple[int, Any]:
        request = urllib.request.Request(
            self.url + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "apikey": self.anon_key,
                "Authorization": f"Bearer {token or self.anon_key}",
                "Content-Type": "application/json",
                **(headers or {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read()
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as error:
            raw = error.read()
            try:
                return error.code, json.loads(raw) if raw else None
            except ValueError:
                return error.code, {"message": raw.decode(errors="replace")[:200]}
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise WorkspaceError(
                "Couldn't reach Supabase. Check your internet connection and the SUPABASE_URL in .env."
            ) from error

    # ------------------------------------------------------------------ auth

    def _store_session(self, payload: dict) -> None:
        self._token = payload["access_token"]
        self._refresh = payload.get("refresh_token")
        self._expires_at = time.time() + int(payload.get("expires_in", 3600)) - 60
        self._user_id = payload["user"]["id"]

    def _login(self) -> None:
        status, payload = self._request(
            "POST", "/auth/v1/token?grant_type=password", body={"email": self.email, "password": self.password}
        )
        if status != 200 or not payload or "access_token" not in payload:
            if status in (400, 401, 422):
                raise WorkspaceError(
                    "Supabase rejected SUPABASE_EMAIL / SUPABASE_PASSWORD in .env. Use the same email and "
                    "password you sign in to the website with."
                )
            raise WorkspaceError(f"Couldn't sign in to Supabase (status {status}).")
        self._store_session(payload)

    def _ensure_session(self) -> None:
        if self._token and time.time() < self._expires_at:
            return
        if self._refresh:
            status, payload = self._request(
                "POST", "/auth/v1/token?grant_type=refresh_token", body={"refresh_token": self._refresh}
            )
            if status == 200 and payload and "access_token" in payload:
                self._store_session(payload)
                return
        self._login()

    def _rest(self, method: str, query: str, *, body: Any = None, prefer: str | None = None) -> tuple[int, Any]:
        self._ensure_session()
        headers = {"Prefer": prefer} if prefer else None
        status, payload = self._request(method, f"/rest/v1/app_state?{query}", body=body, token=self._token, headers=headers)
        if status == 401:                      # token rejected: sign in again once
            self._token = None
            self._ensure_session()
            status, payload = self._request(method, f"/rest/v1/app_state?{query}", body=body, token=self._token, headers=headers)
        return status, payload

    @staticmethod
    def _explain(status: int, payload: Any) -> WorkspaceError:
        code = (payload or {}).get("code", "") if isinstance(payload, dict) else ""
        message = (payload or {}).get("message", "") if isinstance(payload, dict) else ""
        if code == "42703" or "rev" in message and "does not exist" in message:
            return WorkspaceError(
                "Your database needs a one-time update. In Supabase open SQL Editor and run "
                "supabase/002_add_rev.sql from the Marginalia repo."
            )
        if code == "42501" or "permission denied" in message:
            return WorkspaceError(
                "Your database is missing permission for signed-in users. In Supabase open SQL Editor, run: "
                "grant select, insert, update on public.app_state to authenticated;"
            )
        if code in ("42P01", "PGRST205"):
            return WorkspaceError("The app_state table doesn't exist. Run supabase/schema.sql in the Supabase SQL Editor.")
        return WorkspaceError(f"Supabase returned an error ({status}): {message or 'unknown'}")

    # ------------------------------------------------------------------ data

    def read(self) -> tuple[dict, int]:
        self._ensure_session()
        status, payload = self._rest("GET", f"select=data,rev&user_id=eq.{urllib.parse.quote(self._user_id or '')}")
        if status != 200:
            raise self._explain(status, payload)
        if not payload:
            raise WorkspaceError(
                "No workspace exists yet. Open your Marginalia website once and sign in; that creates it. Then try again."
            )
        data = payload[0]["data"]
        if not isinstance(data, dict) or "academics" not in data or "people" not in data:
            raise WorkspaceError("The saved workspace looks unreadable, so nothing was changed.")
        return data, int(payload[0]["rev"])

    def _write(self, data: dict, expected_rev: int) -> bool:
        """True if saved; False if the website saved first (the version moved on)."""
        query = f"user_id=eq.{urllib.parse.quote(self._user_id or '')}&rev=eq.{expected_rev}"
        status, payload = self._rest("PATCH", query, body={"data": data}, prefer="return=representation")
        if status not in (200, 201, 204):
            raise self._explain(status, payload)
        return bool(payload)

    def update(self, change: Callable[[dict], tuple[Any, bool]]) -> Any:
        """Read the newest workspace, let `change` edit it, and save only if nobody else saved first.

        `change(workspace)` returns (result, should_save). It may raise to stop without saving.
        """
        for _ in range(MAX_ATTEMPTS):
            data, rev = self.read()
            result, should_save = change(data)
            if not should_save:
                return result
            if self._write(data, rev):
                return result
            time.sleep(0.2)                    # the website saved in between: read again and redo the change
        raise WorkspaceError("Your workspace kept changing while saving. Nothing was lost; please try again.")

    def snapshot(self) -> dict:
        return self.read()[0]
