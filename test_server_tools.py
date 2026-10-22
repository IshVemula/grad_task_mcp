import asyncio
import json

import pytest

import server
from security import request_times
from test_supabase_client import EMAIL, PASSWORD, FakeSupabase


def sample_workspace():
    def subject(sid, name):
        return {"id": sid, "name": name, "professor": "", "color": "var(--c-acad)",
                "deadlines": [], "todos": [], "milestones": []}

    return {
        "academics": {"semester": "Fall 2026", "subjects": [subject("s1", "Decision Framing and Analysis"),
                                                             subject("s2", "Applications of AI in Tech Teams")]},
        "lifeadmin": {"documents": [], "home": [], "groceries": [], "bills": [], "appointments": []},
        "career": {"applications": [], "tasks": [], "networking": []},
        "people": [], "personal": {"recreation": [], "social": [], "tasks": []},
    }


@pytest.fixture
def stack(monkeypatch):
    fake = FakeSupabase()
    fake.data = sample_workspace()
    for key, value in {"SUPABASE_URL": fake.url, "SUPABASE_ANON_KEY": "anon",
                       "SUPABASE_EMAIL": EMAIL, "SUPABASE_PASSWORD": PASSWORD}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(server, "_client", None)
    request_times.clear()
    yield fake
    fake.close()


def call(name, **arguments):
    result = asyncio.run(server.mcp.call_tool(name, arguments))
    assert not result.is_error, result.content
    if result.structured_content:
        return result.structured_content
    return json.loads(next(part.text for part in result.content if getattr(part, "text", None)))


def test_the_server_tells_claude_not_to_guess_destinations():
    assert "Never guess" in server.INSTRUCTIONS and "ask them BEFORE" in server.INSTRUCTIONS
    assert "does not fit" in server.INSTRUCTIONS


def test_add_a_deadline_through_the_real_tool(stack):
    out = call("add_academic_item", subject="decision", kind="deadline", title="Assignment 4",
               deadline_type="Assignment", due_date="2026-10-29", due_time="11:59 PM")
    assert out["success"] and out["where"] == "Academics → Decision Framing and Analysis → Upcoming Deadlines"
    saved = stack.data["academics"]["subjects"][0]["deadlines"][0]
    assert saved["date"] == "2026-10-29" and saved["time"] == "23:59" and stack.rev == 2


def test_an_unclear_destination_asks_and_saves_nothing(stack):
    out = call("add_academic_item", subject="Macro", kind="todo", title="Read")
    assert out["success"] is False and out["needs_clarification"] is True
    assert "Decision Framing and Analysis" in out["options"]
    assert stack.patches == 0


def test_something_that_does_not_fit_asks_first(stack):
    out = call("add_life_admin_item", kind="home", title="Cook", due_date="2026-10-15")
    assert out["needs_clarification"] and "Appointments & Errands" in out["options"]
    assert stack.patches == 0


def test_dry_run_previews_without_saving(stack):
    out = call("add_personal_item", kind="recreation", text="Homecoming Game", due_date="2026-10-17", dry_run=True)
    assert out["success"] and out["dry_run"] and "Personal → Recreation" in out["where"]
    assert stack.patches == 0


def test_find_then_complete_by_id(stack):
    call("add_life_admin_item", kind="bill", title="Rent", amount=1400, due_date="2026-10-30", recurring="monthly")
    found = call("find_items", query="rent")
    assert found["count"] == 1
    out = call("complete_item", item_id=found["items"][0]["id"])
    assert out["success"] and stack.data["lifeadmin"]["bills"][0]["paid"] is True


def test_bad_values_are_rejected_before_anything_is_saved(stack):
    out = call("add_life_admin_item", kind="appointment", title="Dentist", due_date="2026-11-03", due_time="25:99")
    assert out["success"] is False and "time" in out["error"]
    assert stack.patches == 0


def test_update_and_delete_by_id(stack):
    call("add_career_item", kind="application", company="Databricks", role="APM")
    app_id = stack.data["career"]["applications"][0]["id"]
    assert call("update_item", item_id=app_id, changes={"status": "Interview"})["success"]
    assert stack.data["career"]["applications"][0]["status"] == "Interview"
    assert call("delete_item", item_id=app_id)["success"]
    assert stack.data["career"]["applications"] == []


def test_deleting_a_subject_asks_first(stack):
    out = call("delete_item", item_id="s1")
    assert out["needs_clarification"] and len(stack.data["academics"]["subjects"]) == 2
    assert call("delete_item", item_id="s1", confirm=True)["success"]
    assert len(stack.data["academics"]["subjects"]) == 1


def test_reading_tools(stack):
    overview = call("get_workspace_overview")
    assert overview["success"] and overview["academics"]["subjects"][0]["name"] == "Decision Framing and Analysis"
    assert call("list_today")["success"] and call("list_upcoming", days=7)["success"]
    assert call("list_items", area="academics", container="AI")["success"]


def test_connection_problems_are_reported_not_raised(stack):
    stack.has_row = False
    out = call("list_today")
    assert out["success"] is False and "Open your Marginalia website" in out["error"]


def test_settings_missing_gives_setup_instructions(monkeypatch):
    monkeypatch.setattr(server, "_client", None)
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_EMAIL", "SUPABASE_PASSWORD"):
        monkeypatch.setenv(key, "")
    monkeypatch.setattr(server, "setting", lambda name: "")
    out = call("list_today")
    assert out["success"] is False and ".env" in out["error"]


def test_the_write_limit_stops_a_runaway_loop(stack):
    for i in range(server.WRITE_LIMIT_PER_MINUTE):
        assert call("add_personal_item", kind="task", text=f"t{i}")["success"]
    out = call("add_personal_item", kind="task", text="one too many")
    assert out["success"] is False and "Rate limit" in out["error"]
