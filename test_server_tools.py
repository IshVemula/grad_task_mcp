import asyncio
import json
from datetime import date

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


def call(tool, /, **arguments):
    result = asyncio.run(server.mcp.call_tool(tool, arguments))
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


def test_waiting_status_works_through_the_real_tools(stack):
    out = call("add_career_item", kind="application", company="Databricks", role="APM", status="Waiting")
    assert out["success"] and stack.data["career"]["applications"][0]["status"] == "Waiting"
    app_id = stack.data["career"]["applications"][0]["id"]
    assert call("update_item", item_id=app_id, changes={"status": "Interview"})["success"]
    assert call("update_item", item_id=app_id, changes={"status": "Waiting"})["success"]


def test_class_times_through_the_real_tools(stack):
    out = call("add_class_time", subject="decision", title="Lecture", days=["Tue", "Thu"], start_time="10:10 AM",
               end_time="11:25 AM", location="Room 204")
    assert out["success"] and out["where"].endswith("→ Class Schedule") and out["repeats"] == "every Tue, Thu, 10:10–11:25"
    saved = stack.data["academics"]["subjects"][0]["schedule"][0]
    assert saved["days"] == [2, 4] and saved["start"] == "10:10" and stack.rev == 2
    # changing it uses a list of days
    assert call("update_item", item_id=saved["id"], changes={"days": ["Mon", "Wed"]})["success"]
    assert stack.data["academics"]["subjects"][0]["schedule"][0]["days"] == [1, 3]
    # an unknown subject asks instead of guessing
    ask = call("add_class_time", subject="Macro", days=["Tue"], start_time="09:00")
    assert ask["needs_clarification"] and stack.patches == 2
    # and a preview changes nothing
    call("add_class_time", subject="AI", days=["Fri"], start_time="13:00", dry_run=True)
    assert len(stack.data["academics"]["subjects"][1].get("schedule", [])) == 0 and stack.patches == 2


def test_dated_career_items_through_the_real_tools(stack):
    out = call("add_career_item", kind="networking", title="Fall Career Fair", due_date="2026-10-30", due_time="10:00 AM")
    assert out["success"] and out["where"] == "Career → Networking"
    saved = stack.data["career"]["networking"][0]
    assert saved["date"] == "2026-10-30" and saved["time"] == "10:00"
    out = call("add_career_item", kind="task", title="Practice case interview", due_date="2026-10-24", due_time="16:00")
    assert out["success"] and stack.data["career"]["tasks"][0]["time"] == "16:00"
    assert call("update_item", item_id=saved["id"], changes={"due_date": "2026-11-02"})["success"]
    assert stack.data["career"]["networking"][0]["date"] == "2026-11-02"
    # an application has no time: Claude is told to ask rather than guess
    ask = call("add_career_item", kind="application", company="Meta", role="PM", due_date="2026-11-05", due_time="09:00")
    assert ask["needs_clarification"] and len(stack.data["career"]["applications"]) == 0


def test_a_dated_subject_todo_through_the_real_tools(stack):
    out = call("add_academic_item", subject="decision", kind="todo", title="Grade the group projects",
               due_date="2026-10-29", due_time="5:00 PM")
    assert out["success"] and out["where"].endswith("→ Things To Do")
    saved = stack.data["academics"]["subjects"][0]["todos"][0]
    assert saved["date"] == "2026-10-29" and saved["time"] == "17:00"
    assert call("update_item", item_id=saved["id"], changes={"due_date": "2026-10-30"})["success"]
    assert stack.data["academics"]["subjects"][0]["todos"][0]["date"] == "2026-10-30"
    # a time with no date asks instead of saving
    ask = call("add_academic_item", subject="decision", kind="todo", title="Call", due_time="09:00")
    assert ask["needs_clarification"] and len(stack.data["academics"]["subjects"][0]["todos"]) == 1


def test_an_event_in_a_space_with_a_person_through_the_real_tools(stack):
    call("add_person", name="Dr. Puga")
    out = call("add_academic_item", subject="decision", kind="event", title="Office hours", due_date=date.today().isoformat(),
               due_time="3:00 PM", end_time="4:00 PM", person="puga")
    assert out["success"] and out["where"].endswith("→ Events & Meetings")
    saved = stack.data["academics"]["subjects"][0]["events"][0]
    assert saved["date"] == date.today().isoformat() and saved["time"] == "15:00" and saved["endTime"] == "16:00"
    assert saved["personId"] == stack.data["people"][0]["id"]
    # an event needs a date; a bad end time is refused; nothing extra was saved
    assert call("add_academic_item", subject="decision", kind="event", title="No date")["needs_clarification"]
    bad = call("add_academic_item", subject="decision", kind="event", title="Backwards", due_date="2026-11-05",
               due_time="16:00", end_time="15:00")
    assert bad["success"] is False and len(stack.data["academics"]["subjects"][0]["events"]) == 1
    # it shows up in Today and can be completed
    today = call("list_upcoming", days=365)
    assert any(e["title"] == "Office hours" and e["person_id"] for e in today["overdue"] + today["upcoming"])
    assert call("complete_item", item_id=saved["id"])["success"] and stack.data["academics"]["subjects"][0]["events"][0]["done"]


def test_a_new_space_has_a_type_and_a_contact_and_an_old_workspace_is_upgraded_on_save(stack):
    out = call("add_subject", name="Robotics Club", space_type="Club", contact="Maya")
    assert out["success"] and out["where"].endswith("new club")
    ws = stack.data
    assert ws["schemaVersion"] == 2
    new = next(s for s in ws["academics"]["subjects"] if s["name"] == "Robotics Club")
    assert (new["type"], new["contact"], new["events"]) == ("Club", "Maya", [])
    # the sample workspace was the old shape: its spaces were upgraded without losing anything
    assert all("professor" not in s and "contact" in s and "events" in s for s in ws["academics"]["subjects"])
    assert call("update_item", item_id=new["id"], changes={"type": "Project", "contact": "Sam"})["success"]
    saved = next(s for s in stack.data["academics"]["subjects"] if s["name"] == "Robotics Club")
    assert (saved["type"], saved["contact"]) == ("Project", "Sam")
    assert call("update_item", item_id=new["id"], changes={"type": "Hobby"})["success"] is False


def test_every_write_records_created_changed_and_finished_times(stack):
    call("add_academic_item", subject="decision", kind="todo", title="Read ch 4")
    todo = stack.data["academics"]["subjects"][0]["todos"][0]
    assert todo["createdAt"] and todo["updatedAt"] and not todo["doneAt"]
    call("complete_item", item_id=todo["id"])
    todo = stack.data["academics"]["subjects"][0]["todos"][0]
    assert todo["doneAt"] and todo["done"] is True
    found = call("find_items", query="Read ch 4")["items"][0]
    assert found["created"] and found["finished"]
    call("complete_item", item_id=todo["id"], done=False)
    assert stack.data["academics"]["subjects"][0]["todos"][0]["doneAt"] == ""
    # a preview records nothing and saves nothing
    patches = stack.patches
    call("add_academic_item", subject="decision", kind="todo", title="Just looking", dry_run=True)
    assert stack.patches == patches


def test_deleting_a_person_unlinks_whatever_was_with_them(stack):
    call("add_person", name="Dr. Puga")
    call("add_academic_item", subject="decision", kind="todo", title="Email about scope", person="puga")
    call("add_personal_item", kind="social", text="Lunch", due_date="2026-11-09", person="puga")
    pid = stack.data["people"][0]["id"]
    assert call("delete_item", item_id=pid, confirm=True)["success"]
    assert stack.data["academics"]["subjects"][0]["todos"][0]["personId"] == ""
    assert stack.data["personal"]["social"][0]["personId"] == ""
