import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from supabase_client import WorkspaceClient, WorkspaceError

EMAIL, PASSWORD = "owner@example.com", "correct horse"


class FakeSupabase:
    """Just enough of Supabase auth + PostgREST, with the same versioning as app_state."""

    def __init__(self):
        self.data = {"academics": {"subjects": []}, "people": [], "marker": "start"}
        self.rev = 1
        self.has_row = True
        self.token = "token-1"
        self.logins = 0
        self.patches = 0
        self.before_patch = None          # callable run once, just before the next PATCH (a website save)
        self.reject_next_token = False
        self.error_for_get = None

        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                length = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(length)) if length else None

            def _authed(self):
                if fake.reject_next_token:
                    fake.reject_next_token = False
                    return False
                return self.headers.get("Authorization") == f"Bearer {fake.token}"

            def do_POST(self):
                body = self._body()
                if urlparse(self.path).path == "/auth/v1/token":
                    if body.get("email") == EMAIL and body.get("password") == PASSWORD:
                        fake.logins += 1
                        fake.token = f"token-{fake.logins}"
                        return self._send(200, {"access_token": fake.token, "refresh_token": "r", "expires_in": 3600,
                                                "user": {"id": "u1"}})
                    return self._send(400, {"message": "Invalid login credentials"})
                self._send(404, {})

            def do_GET(self):
                if not self._authed():
                    return self._send(401, {"message": "JWT expired"})
                if fake.error_for_get:
                    return self._send(*fake.error_for_get)
                self._send(200, [{"data": fake.data, "rev": fake.rev}] if fake.has_row else [])

            def do_PATCH(self):
                if not self._authed():
                    return self._send(401, {"message": "JWT expired"})
                if fake.before_patch:
                    hook, fake.before_patch = fake.before_patch, None
                    hook()
                body = self._body()
                expected = int(parse_qs(urlparse(self.path).query)["rev"][0].removeprefix("eq."))
                fake.patches += 1
                if expected != fake.rev:
                    return self._send(200, [])
                fake.data = body["data"]
                fake.rev += 1
                self._send(200, [{"rev": fake.rev}])

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def fake():
    server = FakeSupabase()
    yield server
    server.close()


def make(fake, **overrides):
    args = {"url": fake.url, "anon_key": "anon", "email": EMAIL, "password": PASSWORD, **overrides}
    return WorkspaceClient(**args)


def test_update_saves_and_bumps_the_version(fake):
    client = make(fake)

    def change(ws):
        ws["marker"] = "changed"
        return "done", True

    assert client.update(change) == "done"
    assert fake.data["marker"] == "changed" and fake.rev == 2


def test_nothing_is_saved_when_the_change_says_not_to(fake):
    client = make(fake)
    client.update(lambda ws: ("dry", False))
    assert fake.patches == 0 and fake.rev == 1


def test_an_error_from_the_change_saves_nothing(fake):
    client = make(fake)

    def refuse(ws):
        raise ValueError("no")

    with pytest.raises(ValueError):
        client.update(refuse)
    assert fake.patches == 0


def test_if_the_website_saves_first_the_change_is_redone_on_the_newest_data(fake):
    client = make(fake)

    def website_saves():                          # the website adds something while we are mid-save
        fake.data = {**fake.data, "from_website": True}
        fake.rev += 1

    fake.before_patch = website_saves
    seen = []

    def change(ws):
        seen.append(dict(ws))
        ws["from_claude"] = True
        return "ok", True

    client.update(change)
    assert len(seen) == 2 and "from_website" not in seen[0] and seen[1]["from_website"] is True
    assert fake.data["from_website"] is True and fake.data["from_claude"] is True      # both survive
    assert fake.rev == 3


def test_wrong_password_says_what_to_fix(fake):
    with pytest.raises(WorkspaceError, match="SUPABASE_PASSWORD"):
        make(fake, password="wrong").snapshot()


def test_missing_settings_are_listed(fake):
    with pytest.raises(WorkspaceError, match="SUPABASE_PASSWORD"):
        make(fake, password="")


def test_no_workspace_yet_tells_you_to_open_the_website(fake):
    fake.has_row = False
    with pytest.raises(WorkspaceError, match="Open your Marginalia website"):
        make(fake).snapshot()


def test_an_expired_token_signs_in_again(fake):
    client = make(fake)
    client.snapshot()
    fake.reject_next_token = True
    client.snapshot()
    assert fake.logins == 2


def test_missing_version_column_points_at_the_migration(fake):
    fake.error_for_get = (400, {"code": "42703", "message": "column app_state.rev does not exist"})
    with pytest.raises(WorkspaceError, match="002_add_rev.sql"):
        make(fake).snapshot()


def test_unreachable_server_is_a_clear_error():
    client = WorkspaceClient("http://127.0.0.1:9", "anon", EMAIL, PASSWORD)
    with pytest.raises(WorkspaceError, match="Couldn't reach Supabase"):
        client.snapshot()


def test_unreadable_saved_data_is_never_touched(fake):
    fake.data = {"nonsense": True}
    with pytest.raises(WorkspaceError, match="unreadable"):
        make(fake).update(lambda ws: ("x", True))
    assert fake.patches == 0
