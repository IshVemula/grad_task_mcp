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
    assert any("other than weekly" in line for line in o["not_supported"])      # weekly classes are supported now
    assert not any("class" in line.lower() and "weekly" not in line.lower() for line in o["not_supported"])


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
    # once you are waiting to hear back, the date is no longer a deadline: nothing is upcoming or overdue
    assert not any(e["title"] == "Databricks" for e in w.list_upcoming(ws, TODAY, 14)["upcoming"])


def test_an_application_has_one_date_that_only_counts_as_a_deadline_until_you_apply(ws):
    app = ws["career"]["applications"][0]
    assert "applied" not in w.add_career_item(ws, "application", company="Meta", role="PM", due_date=date(2026, 11, 1))["item"]
    titles = lambda: [e["title"] for e in w.list_upcoming(ws, TODAY, 14)["upcoming"]]
    assert "Databricks" in titles()                          # Interested: the date is a deadline
    w.update_item(ws, "a1", {"status": "Preparing"})
    assert "Databricks" in titles()                          # Preparing: still a deadline
    for status in ("Applied", "Interview", "Waiting", "Offer", "Rejected"):
        w.update_item(ws, "a1", {"status": status})
        assert "Databricks" not in titles(), status          # after applying: just the day you applied
    app["deadline"] = "2026-10-01"                           # a past date on an applied application is not overdue
    assert "Databricks" not in [e["title"] for e in w.list_upcoming(ws, TODAY, 14)["overdue"]]
    with pytest.raises(ValueError):
        w.update_item(ws, "a1", {"applied_date": "2026-10-19"})   # the second date no longer exists


# ---------------------------------------------------------------- repeating class times

THURSDAY = date(2026, 10, 22)
assert THURSDAY.weekday() == 3


def test_a_class_time_is_stored_the_way_the_website_stores_it(ws):
    result = w.add_class_time(ws, "applications of ai", "Lecture", ["Tue", "Thu"], "8:40 AM", "9:55 AM", "Room 120")
    c = ws["academics"]["subjects"][1]["schedule"][0]
    assert set(c) == {"id", "title", "days", "start", "end", "location", "from", "until"}
    assert c["days"] == [2, 4] and c["start"] == "08:40" and c["end"] == "09:55" and c["location"] == "Room 120"
    assert result["where"] == "Academics → Applications of AI in Tech Teams → Class Schedule"
    assert result["repeats"] == "every Tue, Thu, 08:40–09:55"


def test_day_names_are_understood_in_several_forms(ws):
    assert w.to_days("Tue, Thu") == [2, 4]
    assert w.to_days(["Tuesday", "thu", 0]) == [0, 2, 4]
    assert w.to_days("Mon/Wed/Fri") == [1, 3, 5]
    with pytest.raises(ValueError):
        w.to_days(["Funday"])
    with pytest.raises(NeedsClarification) as ask:
        w.to_days([])
    assert ask.value.options[0] == "Mon"


def test_a_class_time_asks_when_something_is_missing_and_saves_nothing(ws):
    before = copy.deepcopy(ws)
    with pytest.raises(NeedsClarification):
        w.add_class_time(ws, "AI", "Lecture", None, "08:40")                    # which days?
    with pytest.raises(NeedsClarification):
        w.add_class_time(ws, "AI", "Lecture", ["Tue"], None)                    # what time?
    with pytest.raises(NeedsClarification):
        w.add_class_time(ws, "Macro", "Lecture", ["Tue"], "08:40")              # unknown subject
    with pytest.raises(ValueError):
        w.add_class_time(ws, "AI", "Lecture", ["Tue"], "09:55", "08:40")        # ends before it starts
    with pytest.raises(ValueError):
        w.add_class_time(ws, "AI", "Lecture", ["Tue"], "08:40", first_day=date(2026, 12, 1), last_day=date(2026, 9, 1))
    assert ws == before


def test_works_on_older_data_with_no_schedule_key(ws):
    assert all("schedule" not in s for s in ws["academics"]["subjects"])
    w.add_class_time(ws, "decision", "Lecture", ["Tue", "Thu"], "10:10", "11:25")
    assert len(ws["academics"]["subjects"][0]["schedule"]) == 1


def test_classes_are_listed_apart_from_deadlines(ws):
    w.add_class_time(ws, "AI", "Lecture", ["Tue", "Thu"], "08:40", "09:55", "Room 120")
    w.add_class_time(ws, "decision", "Lecture", ["Tue", "Thu"], "10:10", "11:25")
    today = w.list_today(ws, THURSDAY)
    assert [(e["title"], e["due_time"], e["end_time"]) for e in today["classes_today"]] == [
        ("Applications of AI in Tech Teams — Lecture", "08:40", "09:55"),
        ("Decision Framing and Analysis — Lecture", "10:10", "11:25"),
    ]
    assert not any(e.get("repeating") for items in today["due_today_or_overdue"].values() for e in items)
    up = w.list_upcoming(ws, THURSDAY, 14)
    assert sorted({e["due_date"] for e in up["classes"]}) == ["2026-10-22", "2026-10-27", "2026-10-29", "2026-11-03", "2026-11-05"]
    assert not any(e.get("repeating") for e in up["upcoming"] + up["overdue"])


def test_first_and_last_day_bound_a_class(ws):
    w.add_class_time(ws, "AI", "Lecture", ["Tue", "Thu"], "08:40", first_day=date(2026, 10, 27), last_day=date(2026, 10, 29))
    days = [e["due_date"] for e in w.list_upcoming(ws, THURSDAY, 14)["classes"]]
    assert days == ["2026-10-27", "2026-10-29"]
    assert w.list_today(ws, THURSDAY)["classes_today"] == []


def test_changing_and_removing_a_class_time(ws):
    w.add_class_time(ws, "AI", "Lecture", ["Tue", "Thu"], "08:40", "09:55")
    cid = ws["academics"]["subjects"][1]["schedule"][0]["id"]
    w.update_item(ws, cid, {"days": ["Mon", "Wed"], "start_time": "09:00", "end_time": "10:15", "location": "Room 2"})
    c = ws["academics"]["subjects"][1]["schedule"][0]
    assert c["days"] == [1, 3] and c["start"] == "09:00" and c["end"] == "10:15" and c["location"] == "Room 2"
    with pytest.raises(ValueError):
        w.update_item(ws, cid, {"end_time": "08:00"})              # would end before it starts
    with pytest.raises(ValueError):
        w.update_item(ws, cid, {"due_date": "2026-10-30"})         # a class time has no due date
    with pytest.raises(ValueError):
        w.complete_item(ws, cid)                                   # and can't be "done"
    assert w.find_items(ws, "lecture")["items"][0]["kind"] == "academics.class"
    w.delete_item(ws, cid)
    assert ws["academics"]["subjects"][1]["schedule"] == []


def test_listing_and_overview_include_class_times(ws):
    w.add_class_time(ws, "AI", "Lecture", ["Tue", "Thu"], "08:40", "09:55")
    listed = w.list_items(ws, "academics", "AI")["items"]
    cls = next(i for i in listed if i["kind"] == "academics.class")
    assert cls["repeats_every"] == "Tue, Thu" and cls["start_time"] == "08:40"
    o = w.overview(ws, THURSDAY)
    assert o["academics"]["subjects"][1]["class_times"] == 1
    assert any("other than weekly" in line for line in o["not_supported"])


def test_deleting_a_subject_mentions_its_class_times(ws):
    w.add_class_time(ws, "AI", "Lecture", ["Tue"], "08:40")
    with pytest.raises(NeedsClarification) as ask:
        w.delete_item(ws, "s-ai")
    assert "class times" in ask.value.question


# ---------------------------------------------------------------- dates and times on career tasks and networking


def test_career_tasks_and_networking_take_a_date_and_time_in_the_websites_shape(ws):
    task = w.add_career_item(ws, "task", "Practice case interview", due_date=date(2026, 10, 24), due_time="4:00 PM")["item"]
    event = w.add_career_item(ws, "networking", "Fall Career Fair", due_date=date(2026, 10, 30), due_time="10:00", person="puga")["item"]
    assert set(task) == {"id", "text", "done", "date", "time"} and task["date"] == "2026-10-24" and task["time"] == "16:00"
    assert set(event) == {"id", "text", "done", "personId", "date", "time"} and event["personId"] == "p1" and event["time"] == "10:00"
    undated = w.add_career_item(ws, "networking", "Email Mark")["item"]
    assert undated["date"] == "" and undated["time"] == ""                       # still fine without a date


def test_dated_career_items_show_up_in_today_and_upcoming_and_drop_off_when_done(ws):
    w.add_career_item(ws, "task", "Send follow-up", due_date=TODAY)
    w.add_career_item(ws, "networking", "Coffee chat", due_date=date(2026, 10, 25), due_time="09:30")
    w.add_career_item(ws, "networking", "Missed thank-you", due_date=date(2026, 10, 20))
    today = w.list_today(ws, TODAY)["due_today_or_overdue"]["career"]
    assert {e["title"] for e in today} == {"Send follow-up", "Missed thank-you"}
    assert next(e for e in today if e["title"] == "Missed thank-you")["overdue"] is True
    up = w.list_upcoming(ws, TODAY, 14)["upcoming"]
    assert any(e["title"] == "Coffee chat" and e["due_time"] == "09:30" for e in up)
    done_id = next(e["id"] for e in today if e["title"] == "Send follow-up")
    w.complete_item(ws, done_id)
    assert {e["title"] for e in w.list_today(ws, TODAY)["due_today_or_overdue"]["career"]} == {"Missed thank-you"}


def test_a_career_date_or_time_can_be_changed_and_cleared(ws):
    cid = w.add_career_item(ws, "task", "Update resume")["item"]["id"]
    w.update_item(ws, cid, {"due_date": "2026-10-27", "due_time": "13:15"})
    item = ws["career"]["tasks"][-1]
    assert item["date"] == "2026-10-27" and item["time"] == "13:15"
    w.update_item(ws, cid, {"due_date": "", "due_time": ""})
    assert item["date"] == "" and item["time"] == ""
    nid = ws["career"]["networking"][0]["id"]
    w.update_item(ws, nid, {"due_date": "2026-10-29", "due_time": "18:00"})
    assert ws["career"]["networking"][0]["date"] == "2026-10-29"


def test_career_dates_ask_when_something_does_not_fit(ws):
    before = copy.deepcopy(ws)
    with pytest.raises(NeedsClarification) as ask:
        w.add_career_item(ws, "task", "Call recruiter", due_time="10:00")                       # a time with no date
    assert "date" in ask.value.question.lower()
    with pytest.raises(NeedsClarification) as ask:
        w.add_career_item(ws, "application", company="Meta", role="PM", due_date=date(2026, 11, 1), due_time="10:00")
    assert "Applications have one date and no time" in ask.value.question and ask.value.options
    assert ws == before
