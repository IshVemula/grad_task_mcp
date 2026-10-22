import copy
from datetime import date

import pytest

import workspace as w
from workspace import NeedsClarification

TODAY = date(2026, 10, 22)


def mk(text, done=False, **extra):
    return {"id": w.new_id(), "text": text, "done": done, **extra}


@pytest.fixture
def ws():
    """A small workspace in the same shape the website saves."""
    return {
        "academics": {
            "semester": "Fall 2026",
            "subjects": [
                {"id": "s-dfa", "name": "Decision Framing and Analysis", "professor": "", "color": "var(--c-acad)",
                 "deadlines": [{"id": "d1", "title": "Assignment 3", "type": "Assignment", "date": "2026-10-22",
                                "time": "12:00", "status": "Not started"}],
                 "todos": [mk("Read ch 4")], "milestones": []},
                {"id": "s-ai", "name": "Applications of AI in Tech Teams", "professor": "", "color": "var(--c-career)",
                 "deadlines": [], "todos": [], "milestones": []},
                {"id": "s-sm", "name": "Strategic Management of Tech and Innovation", "professor": "",
                 "color": "var(--c-people)", "deadlines": [], "todos": [], "milestones": []},
                {"id": "s-sm2", "name": "Strategic Finance", "professor": "", "color": "var(--c-personal)",
                 "deadlines": [], "todos": [], "milestones": []},
            ],
        },
        "lifeadmin": {
            "documents": [{"id": "doc1", "name": "OPT application", "deadline": "2026-11-05", "status": "In Progress",
                           "link": "", "notes": ""}],
            "home": [mk("Laundry", recur="weekly")],
            "groceries": [],
            "bills": [{"id": "b1", "name": "Rent", "amount": 1400, "due": "2026-10-30", "paid": False, "recur": "monthly"},
                      {"id": "b2", "name": "Wi-Fi", "amount": 50, "due": "2026-10-20", "paid": False, "recur": "monthly"}],
            "appointments": [],
        },
        "career": {
            "applications": [{"id": "a1", "company": "Databricks", "role": "APM", "deadline": "2026-10-25",
                              "applied": "", "status": "Interested"}],
            "tasks": [], "networking": [mk("Follow up", personId="p1")],
        },
        "people": [{"id": "p1", "name": "Ricardo Puga", "org": "Cornell", "role": "Professor", "how": "", "last": "",
                    "next": "2026-10-22", "notes": "", "tasks": [mk("Send grant requirements")]}],
        "personal": {
            "recreation": [mk("Homecoming Game", date="2026-10-17", time="")],
            "social": [], "tasks": [],
        },
    }


# ---------------------------------------------------------------- placing things


def test_deadline_lands_in_the_named_subject_with_the_websites_shape(ws):
    result = w.add_academic_item(ws, "decision framing", "deadline", "Quiz", "Quiz", date(2026, 10, 22), "10:00")
    item = ws["academics"]["subjects"][0]["deadlines"][-1]
    assert set(item) == {"id", "title", "type", "date", "time", "status"}
    assert item["type"] == "Quiz" and item["date"] == "2026-10-22" and item["time"] == "10:00"
    assert item["status"] == "Not started"
    assert result["where"] == "Academics → Decision Framing and Analysis → Upcoming Deadlines"


def test_unknown_subject_asks_instead_of_guessing_or_creating(ws):
    before = copy.deepcopy(ws)
    with pytest.raises(NeedsClarification) as ask:
        w.add_academic_item(ws, "Macroeconomics", "todo", "Read ch 1")
    assert "Decision Framing and Analysis" in ask.value.options
    assert ws == before


def test_ambiguous_subject_asks_which_one(ws):
    with pytest.raises(NeedsClarification) as ask:
        w.add_academic_item(ws, "Strat", "todo", "Read")
    assert set(ask.value.options) == {"Strategic Management of Tech and Innovation", "Strategic Finance"}


def test_missing_subject_asks(ws):
    with pytest.raises(NeedsClarification):
        w.add_academic_item(ws, None, "todo", "Read")


def test_deadline_without_a_date_asks(ws):
    with pytest.raises(NeedsClarification):
        w.add_academic_item(ws, "AI", "deadline", "Short Quiz")


def test_things_that_do_not_fit_ask_first(ws):
    before = copy.deepcopy(ws)
    cases = [
        lambda: w.add_academic_item(ws, "AI", "todo", "Class", due_date=date(2026, 10, 22)),       # to-dos have no date
        lambda: w.add_life_admin_item(ws, "home", "Cook", due_date=date(2026, 10, 15)),              # chores have no date
        lambda: w.add_personal_item(ws, "task", "Call mom", due_date=date(2026, 10, 25)),            # personal tasks have no date
        lambda: w.add_career_item(ws, "networking", "Email Mark", due_date=date(2026, 10, 25)),      # follow-ups have no date
    ]
    for case in cases:
        with pytest.raises(NeedsClarification) as ask:
            case()
        assert ask.value.options
    assert ws == before


def test_bill_needs_amount_and_due_date(ws):
    with pytest.raises(NeedsClarification):
        w.add_life_admin_item(ws, "bill", "Phone", due_date=date(2026, 11, 1))
    with pytest.raises(NeedsClarification):
        w.add_life_admin_item(ws, "bill", "Phone", amount=35)
    w.add_life_admin_item(ws, "bill", "Phone", due_date=date(2026, 11, 1), amount=35, recurring="monthly")
    bill = ws["lifeadmin"]["bills"][-1]
    assert set(bill) == {"id", "name", "amount", "due", "paid", "recur"}
    assert bill["amount"] == 35 and bill["paid"] is False and bill["recur"] == "monthly"


def test_dry_run_changes_nothing_but_reports_the_destination(ws):
    before = copy.deepcopy(ws)
    result = w.add_life_admin_item(ws, "grocery", "Milk", group="Dairy", dry_run=True)
    assert ws == before
    assert result["dry_run"] and "Groceries" in result["where"]


def test_appointment_time_parsing(ws):
    w.add_life_admin_item(ws, "appointment", "Dentist", due_date=date(2026, 11, 3), due_time="2:30 PM")
    assert ws["lifeadmin"]["appointments"][-1]["time"] == "14:30"
    with pytest.raises(ValueError):
        w.add_life_admin_item(ws, "appointment", "Dentist", due_date=date(2026, 11, 3), due_time="25:99")


def test_application_and_networking_link_to_existing_person_only(ws):
    w.add_career_item(ws, "application", company="Google", role="APM Intern")
    assert ws["career"]["applications"][-1]["status"] == "Interested"
    w.add_career_item(ws, "networking", "Thank you note", person="puga")
    assert ws["career"]["networking"][-1]["personId"] == "p1"
    with pytest.raises(NeedsClarification):
        w.add_career_item(ws, "networking", "Hi", person="Nobody Here")
    with pytest.raises(NeedsClarification):
        w.add_career_item(ws, "application", company="Google")   # role missing


def test_person_and_person_task(ws):
    w.add_person(ws, "Anika Rao", organization="Meridian", next_followup=date(2026, 10, 30))
    assert ws["people"][-1]["next"] == "2026-10-30" and ws["people"][-1]["tasks"] == []
    w.add_person_task(ws, "anika", "Send resume")
    assert ws["people"][-1]["tasks"][0]["text"] == "Send resume"
    with pytest.raises(ValueError):
        w.add_person(ws, "anika rao")


def test_new_subject_gets_a_color_and_duplicates_are_refused(ws):
    w.add_subject(ws, "Statistics", "Prof. Okafor")
    s = ws["academics"]["subjects"][-1]
    assert s["color"] == w.SUBJECT_COLORS[4 % 5] and s["deadlines"] == []
    with pytest.raises(ValueError):
        w.add_subject(ws, "statistics")


def test_titles_are_cleaned_and_limited(ws):
    w.add_academic_item(ws, "AI", "todo", "  Read\x00 this  ")
    assert ws["academics"]["subjects"][1]["todos"][-1]["text"] == "Read this"
    with pytest.raises(ValueError):
        w.add_academic_item(ws, "AI", "todo", "x" * 201)


# ---------------------------------------------------------------- reading


def test_today_and_upcoming_match_the_website(ws):
    today = w.list_today(ws, TODAY)["due_today_or_overdue"]
    assert {e["title"] for e in today["academics"]} == {"Assignment 3"}
    assert [e["title"] for e in today["life_admin"]] == ["Wi-Fi"] and today["life_admin"][0]["overdue"]
    assert [e["title"] for e in today["people"]] == ["Ricardo Puga"]
    assert "career" not in today
    up = w.list_upcoming(ws, TODAY, 14)
    # same order as the website: by date, and on the same day untimed items come before timed ones
    assert [e["title"] for e in up["upcoming"]] == ["Ricardo Puga", "Assignment 3", "Databricks", "Rent", "OPT application"]
    assert [e["title"] for e in up["overdue"]] == ["Homecoming Game", "Wi-Fi"]


def test_completed_items_drop_out_of_today(ws):
    w.complete_item(ws, "d1")
    assert "academics" not in w.list_today(ws, TODAY)["due_today_or_overdue"]


def test_list_and_find(ws):
    assert w.list_items(ws, "life_admin", "bills")["count"] == 2
    assert w.list_items(ws, "academics", "decision")["count"] == 3          # subject + deadline + todo
    assert w.list_items(ws, "people", "Ricardo")["count"] == 2
    with pytest.raises(NeedsClarification):
        w.list_items(ws, "life_admin", "nonsense")
    assert w.find_items(ws, "rent")["items"][0]["id"] == "b1"


def test_overview_lists_real_names_and_what_is_unsupported(ws):
    o = w.overview(ws, TODAY)
    assert [s["name"] for s in o["academics"]["subjects"]][0] == "Decision Framing and Analysis"
    assert o["people"][0]["name"] == "Ricardo Puga"
    assert any("class" in line.lower() for line in o["not_supported"])


# ---------------------------------------------------------------- changing


def test_update_changes_only_allowed_fields(ws):
    w.update_item(ws, "b1", {"amount": 1450, "due_date": "2026-11-01"})
    bill = ws["lifeadmin"]["bills"][0]
    assert bill["amount"] == 1450 and bill["due"] == "2026-11-01"
    with pytest.raises(ValueError):
        w.update_item(ws, "b1", {"link": "x"})
    with pytest.raises(ValueError):
        w.update_item(ws, "b1", {"amount": "lots"})
    with pytest.raises(ValueError):
        w.update_item(ws, "nope", {"amount": 1})
    with pytest.raises(NeedsClarification):
        w.update_item(ws, "b1", {})


def test_update_can_clear_a_date_and_relink_a_person(ws):
    w.update_item(ws, "a1", {"due_date": ""})
    assert ws["career"]["applications"][0]["deadline"] == ""
    nid = ws["career"]["networking"][0]["id"]
    w.update_item(ws, nid, {"person": ""})
    assert ws["career"]["networking"][0]["personId"] == ""


def test_complete_uses_the_right_field_for_each_kind(ws):
    w.complete_item(ws, "b1")
    w.complete_item(ws, "d1")
    w.complete_item(ws, "doc1")
    assert ws["lifeadmin"]["bills"][0]["paid"] is True
    assert ws["academics"]["subjects"][0]["deadlines"][0]["status"] == "Done"
    assert ws["lifeadmin"]["documents"][0]["status"] == "Complete"
    w.complete_item(ws, "b1", done=False)
    assert ws["lifeadmin"]["bills"][0]["paid"] is False
    with pytest.raises(ValueError):
        w.complete_item(ws, "a1")


def test_deleting_containers_needs_confirmation_and_unlinks(ws):
    with pytest.raises(NeedsClarification):
        w.delete_item(ws, "p1")
    assert len(ws["people"]) == 1
    w.delete_item(ws, "p1", confirm=True)
    assert ws["people"] == [] and ws["career"]["networking"][0]["personId"] == ""
    with pytest.raises(NeedsClarification):
        w.delete_item(ws, "s-dfa")
    w.delete_item(ws, "b2")                       # a single bill needs no confirmation
    assert [b["id"] for b in ws["lifeadmin"]["bills"]] == ["b1"]


def test_waiting_is_a_status_for_applications_right_after_interview(ws):
    assert w.APP_STATUS.index("Waiting") == w.APP_STATUS.index("Interview") + 1
    w.add_career_item(ws, "application", company="Google", role="APM Intern", status="waiting")
    assert ws["career"]["applications"][-1]["status"] == "Waiting"
    w.update_item(ws, "a1", {"status": "Interview"})
    w.update_item(ws, "a1", {"status": "Waiting"})
    assert ws["career"]["applications"][0]["status"] == "Waiting"
    # a pending application is still open: its deadline keeps showing in Upcoming
    assert any(e["title"] == "Databricks" for e in w.list_upcoming(ws, TODAY, 14)["upcoming"])
