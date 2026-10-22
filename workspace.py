"""Operations on the Marginalia workspace: the JSON document the website keeps in Supabase.

Every function takes the workspace dict and changes it in place. None of them guess:
if a destination is missing, unknown, or ambiguous, or the item doesn't fit any list
the website has, they raise NeedsClarification so the caller asks the user *before*
anything is written.
"""

from __future__ import annotations

import re
import uuid
from collections import namedtuple
from datetime import date, datetime, timedelta
from typing import Any, Iterator

AREAS = ("academics", "life_admin", "career", "people", "personal")

DEADLINE_TYPES = ["Assignment", "Exam", "Project", "Presentation", "Reading", "Quiz"]
DEADLINE_STATUS = ["Not started", "In progress", "Done"]
DOC_STATUS = ["Not Started", "In Progress", "Submitted", "Waiting", "Complete"]
APP_STATUS = ["Interested", "Preparing", "Applied", "Interview", "Waiting", "Offer", "Rejected", "Closed"]
RECUR = ["none", "daily", "weekly", "monthly"]
GROCERY_GROUPS = ["Produce", "Dairy", "Pantry", "Household", "Other"]
SUBJECT_COLORS = [
    "var(--c-acad)", "var(--c-career)", "var(--c-people)", "var(--c-personal)", "var(--c-admin)",
]

LIFE_ADMIN_LISTS = ["documents", "home", "groceries", "bills", "appointments"]
CAREER_LISTS = ["applications", "tasks", "networking"]
PERSONAL_LISTS = ["recreation", "social", "tasks"]

MAX_SHORT = 200
MAX_LONG = 2000


class NeedsClarification(Exception):
    """Nothing was written: the user needs to say where this goes or fill something in."""

    def __init__(self, question: str, options: list[str] | None = None):
        super().__init__(question)
        self.question = question
        self.options = options or []

    def as_response(self) -> dict:
        response: dict[str, Any] = {
            "success": False,
            "needs_clarification": True,
            "question": self.question,
            "note": "Nothing was saved. Ask the user this question, then try again with their answer.",
        }
        if self.options:
            response["options"] = self.options
        return response


# --------------------------------------------------------------------------- values

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_TIME = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])?\s*$")


def new_id() -> str:
    return str(uuid.uuid4())


def clean(value: Any, field: str, *, required: bool = True, max_len: int = MAX_SHORT) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise NeedsClarification(f"What should the {field} be?")
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text.")
    value = _CONTROL.sub("", value).strip()
    if len(value) > max_len:
        raise ValueError(f"{field} cannot exceed {max_len} characters.")
    return value


def to_date(value: Any, field: str, *, required: bool = False, ask: str | None = None) -> str:
    if value is None or value == "":
        if required:
            raise NeedsClarification(ask or f"What is the {field}?")
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            pass
    raise ValueError(f"{field} must be a calendar date like 2026-10-22.")


def to_time(value: Any, field: str = "time") -> str:
    if value is None or value == "":
        return ""
    match = _TIME.match(str(value))
    if not match:
        raise ValueError(f"{field} must look like 14:30 or 2:30 PM.")
    hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3)
    if meridiem:
        if not 1 <= hour <= 12:
            raise ValueError(f"{field} must look like 14:30 or 2:30 PM.")
        hour = hour % 12 + (12 if meridiem.lower() == "pm" else 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"{field} must look like 14:30 or 2:30 PM.")
    return f"{hour:02d}:{minute:02d}"


def to_choice(value: Any, options: list[str], field: str, default: str | None = None) -> str:
    if value is None or value == "":
        if default is not None:
            return default
        raise NeedsClarification(f"Which {field}?", options)
    for option in options:
        if str(value).strip().lower() == option.lower():
            return option
    raise ValueError(f"{field} must be one of: {', '.join(options)}.")


def to_amount(value: Any) -> float | int:
    if value is None or value == "":
        raise NeedsClarification("What is the amount?")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("amount must be a number.") from None
    if number < 0:
        raise ValueError("amount cannot be negative.")
    number = round(number, 2)
    return int(number) if number == int(number) else number


def to_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be true or false.")


WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]          # 0 = Sunday, as the website stores them
_FULL_DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
_DAY_NUMBERS = {**{n.lower(): i for i, n in enumerate(WEEKDAYS)}, **{n.lower(): i for i, n in enumerate(_FULL_DAYS)}}
MONDAY_FIRST = WEEKDAYS[1:] + WEEKDAYS[:1]


def to_days(value: Any) -> list[int]:
    if value is None or value == [] or value == "":
        raise NeedsClarification("Which days of the week does it meet?", MONDAY_FIRST)
    if isinstance(value, str):
        value = [part for part in re.split(r"[,\s/&]+", value) if part]
    found: set[int] = set()
    for item in value:
        if isinstance(item, int) and not isinstance(item, bool) and 0 <= item <= 6:
            found.add(item)
        elif str(item).strip().lower() in _DAY_NUMBERS:
            found.add(_DAY_NUMBERS[str(item).strip().lower()])
        else:
            raise ValueError(f"'{item}' isn't a day of the week. Use Mon, Tue, Wed, Thu, Fri, Sat or Sun.")
    return sorted(found)


def days_label(days: list[int]) -> str:
    return ", ".join(WEEKDAYS[d] for d in sorted(days, key=lambda d: (d + 6) % 7))


def check_class(item: dict) -> None:
    if not item.get("start"):
        raise NeedsClarification("What time does it start?")
    if item.get("end") and item["end"] <= item["start"]:
        raise ValueError("The end time must be after the start time.")
    if item.get("from") and item.get("until") and item["until"] < item["from"]:
        raise ValueError("The last day is before the first day.")


def meets_on(c: dict, day: date) -> bool:
    iso = day.isoformat()
    return ((day.weekday() + 1) % 7 in c.get("days", [])
            and (not c.get("from") or iso >= c["from"]) and (not c.get("until") or iso <= c["until"]))


def next_session(c: dict, today: date) -> str:
    for offset in range(400):
        if meets_on(c, today + timedelta(days=offset)):
            return (today + timedelta(days=offset)).isoformat()
    return ""


# --------------------------------------------------------------------------- lookups


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def resolve(label: str, query: str | None, candidates: list[tuple[str, str]]) -> str:
    """Return the id of the one candidate that matches, or ask. candidates = [(id, name)]."""
    names = [name for _, name in candidates]
    q = _norm(query or "")
    if not q:
        raise NeedsClarification(f"Which {label} is this for?", names)

    for cid, _ in candidates:
        if q == cid.lower():
            return cid

    def pick(matches: list[tuple[str, str]]) -> str | None:
        if len(matches) == 1:
            return matches[0][0]
        if len(matches) > 1:
            raise NeedsClarification(
                f"'{query}' matches more than one {label}. Which one?", [n for _, n in matches]
            )
        return None

    for matches in (
        [c for c in candidates if _norm(c[1]) == q],
        [c for c in candidates if _norm(c[1]).startswith(q)],
        [c for c in candidates if q in _norm(c[1])],
    ):
        found = pick(matches)
        if found:
            return found

    raise NeedsClarification(
        f"I couldn't find a {label} called '{query}'. Which one did you mean? "
        f"(Or tell me to create it.)",
        names,
    )


def subjects(ws: dict) -> list[dict]:
    return ws["academics"]["subjects"]


def find_subject(ws: dict, query: str | None) -> dict:
    cid = resolve("subject", query, [(s["id"], s["name"]) for s in subjects(ws)])
    return next(s for s in subjects(ws) if s["id"] == cid)


def find_person(ws: dict, query: str | None) -> dict:
    cid = resolve("person", query, [(p["id"], p["name"]) for p in ws["people"]])
    return next(p for p in ws["people"] if p["id"] == cid)


# --------------------------------------------------------------------------- records

Rec = namedtuple("Rec", "kind area where key container item")


def iter_records(ws: dict) -> Iterator[Rec]:
    """Every item in the workspace, with where it lives on the website."""
    for s in subjects(ws):
        yield Rec("academics.subject", "academics", f"Academics → {s['name']}", s["id"], subjects(ws), s)
        for d in s["deadlines"]:
            yield Rec("academics.deadline", "academics", f"Academics → {s['name']} → Upcoming Deadlines", s["id"], s["deadlines"], d)
        for t in s["todos"]:
            yield Rec("academics.todo", "academics", f"Academics → {s['name']} → Things To Do", s["id"], s["todos"], t)
        for m in s["milestones"]:
            yield Rec("academics.milestone", "academics", f"Academics → {s['name']} → Major Milestones", s["id"], s["milestones"], m)
        for c in s.setdefault("schedule", []):
            yield Rec("academics.class", "academics", f"Academics → {s['name']} → Class Schedule", s["id"], s["schedule"], c)
    la = ws["lifeadmin"]
    for key, kind, label in (
        ("documents", "life_admin.document", "Documents"),
        ("home", "life_admin.home", "Home"),
        ("groceries", "life_admin.grocery", "Groceries"),
        ("bills", "life_admin.bill", "Bills & Utilities"),
        ("appointments", "life_admin.appointment", "Appointments & Errands"),
    ):
        for item in la[key]:
            yield Rec(kind, "life_admin", f"Life Admin → {label}", key, la[key], item)
    cr = ws["career"]
    for key, kind, label in (
        ("applications", "career.application", "Applications"),
        ("tasks", "career.task", "Career Tasks"),
        ("networking", "career.networking", "Networking"),
    ):
        for item in cr[key]:
            yield Rec(kind, "career", f"Career → {label}", key, cr[key], item)
    for p in ws["people"]:
        yield Rec("people.person", "people", f"People → {p['name']}", p["id"], ws["people"], p)
        for t in p["tasks"]:
            yield Rec("people.task", "people", f"People → {p['name']} → Linked Tasks", p["id"], p["tasks"], t)
    pr = ws["personal"]
    for key, kind, label in (
        ("recreation", "personal.recreation", "Recreation"),
        ("social", "personal.social", "Social"),
        ("tasks", "personal.task", "Personal Tasks"),
    ):
        for item in pr[key]:
            yield Rec(kind, "personal", f"Personal → {label}", key, pr[key], item)


def _title(item: dict) -> str:
    for key in ("title", "text", "name", "company"):
        if item.get(key):
            return item[key]
    return ""


def _when(rec: Rec) -> tuple[str, str]:
    i = rec.item
    if rec.kind in ("academics.deadline", "academics.milestone", "life_admin.appointment",
                    "personal.recreation", "personal.social"):
        return i.get("date", ""), i.get("time", "")
    if rec.kind == "life_admin.document" or rec.kind == "career.application":
        return i.get("deadline", ""), ""
    if rec.kind == "life_admin.bill":
        return i.get("due", ""), ""
    if rec.kind == "people.person":
        return i.get("next", ""), ""
    return "", ""


def is_done(rec: Rec) -> bool:
    i, k = rec.item, rec.kind
    if k == "academics.deadline":
        return i.get("status") == "Done"
    if k == "life_admin.bill":
        return bool(i.get("paid"))
    if k == "life_admin.document":
        return i.get("status") == "Complete"
    if k == "career.application":
        return i.get("status") in ("Rejected", "Closed")
    if k in ("academics.subject", "people.person"):
        return False
    return bool(i.get("done"))


def summarize(rec: Rec) -> dict:
    due, time = _when(rec)
    out: dict[str, Any] = {
        "id": rec.item["id"], "kind": rec.kind, "where": rec.where, "title": _title(rec.item),
    }
    if due:
        out["due_date"] = due
    if time:
        out["due_time"] = time
    if rec.kind == "academics.deadline":
        out["type"], out["status"] = rec.item.get("type"), rec.item.get("status")
    elif rec.kind == "life_admin.document":
        out["status"] = rec.item.get("status")
    elif rec.kind == "life_admin.bill":
        out["amount"], out["paid"] = rec.item.get("amount"), bool(rec.item.get("paid"))
        out["recurring"] = rec.item.get("recur", "none")
    elif rec.kind == "career.application":
        out["role"], out["status"] = rec.item.get("role", ""), rec.item.get("status")
    elif rec.kind == "people.person":
        out["organization"], out["role"] = rec.item.get("org", ""), rec.item.get("role", "")
        if rec.item.get("last"):
            out["last_contacted"] = rec.item["last"]
    elif rec.kind == "academics.subject":
        out["professor"] = rec.item.get("professor", "")
        out["class_times"] = len(rec.item.get("schedule", []))
    elif rec.kind == "academics.class":
        c = rec.item
        out["repeats_every"], out["start_time"], out["end_time"] = days_label(c["days"]), c.get("start", ""), c.get("end", "")
        out["location"] = c.get("location", "")
        if c.get("from"):
            out["first_day"] = c["from"]
        if c.get("until"):
            out["last_day"] = c["until"]
        out["next_session"] = next_session(c, today_local())
    out["done"] = is_done(rec)
    return out


def find_record(ws: dict, item_id: str) -> Rec:
    for rec in iter_records(ws):
        if rec.item["id"] == item_id:
            return rec
    raise ValueError(
        "No item has that id. Use find_items or list_items to look up the right id, and don't guess one."
    )


# --------------------------------------------------------------------------- reading


def overview(ws: dict, today: date) -> dict:
    la, cr, pr = ws["lifeadmin"], ws["career"], ws["personal"]
    return {
        "today": today.isoformat(),
        "semester": ws["academics"]["semester"],
        "academics": {
            "subjects": [
                {
                    "id": s["id"], "name": s["name"], "professor": s.get("professor", ""),
                    "open_deadlines": sum(1 for d in s["deadlines"] if d.get("status") != "Done"),
                    "open_todos": sum(1 for t in s["todos"] if not t.get("done")),
                    "milestones": len(s["milestones"]),
                    "class_times": len(s.get("schedule", [])),
                }
                for s in subjects(ws)
            ],
            "can_add": "deadline, todo, milestone or a repeating weekly class time on a subject; or a new subject",
        },
        "life_admin": {
            "lists": {
                "documents": len(la["documents"]), "home": len(la["home"]), "groceries": len(la["groceries"]),
                "bills": len(la["bills"]), "appointments": len(la["appointments"]),
            },
        },
        "career": {"lists": {"applications": len(cr["applications"]), "tasks": len(cr["tasks"]),
                             "networking": len(cr["networking"])}},
        "people": [{"id": p["id"], "name": p["name"], "organization": p.get("org", ""), "role": p.get("role", "")}
                   for p in ws["people"]],
        "personal": {"lists": {"recreation": len(pr["recreation"]), "social": len(pr["social"]), "tasks": len(pr["tasks"])}},
        "allowed_values": {
            "deadline_type": DEADLINE_TYPES, "deadline_status": DEADLINE_STATUS,
            "document_status": DOC_STATUS, "application_status": APP_STATUS,
            "recurring": RECUR, "grocery_group": GROCERY_GROUPS,
        },
        "not_supported": [
            "Repeating patterns other than weekly (every other week, monthly): ask the user how they want it handled",
            "One-off calendar events or meetings (use an Appointment, a person follow-up, or a subject to-do only if the user says so)",
            "Personal tasks with dates (use Recreation or Social for dated personal items)",
            "Home tasks with due dates (use Appointments & Errands for dated chores)",
        ],
    }


def dated_entries(ws: dict) -> list[dict]:
    """Everything with a date that is still open (what the website's Today/Upcoming show)."""
    out = []
    for rec in iter_records(ws):
        if is_done(rec):
            continue
        # An application's single date is a deadline only while you are still to apply; after that
        # it is just the day you applied, so it never shows as upcoming or overdue.
        if rec.kind == "career.application" and rec.item.get("status") not in ("Interested", "Preparing"):
            continue
        due, time = _when(rec)
        if not due:
            continue
        entry = summarize(rec)
        entry["area"] = rec.area
        out.append(entry)
    return out


def class_sessions(ws: dict, start: date, days: int) -> list[dict]:
    """Each repeating class time, worked out for the days from `start` (never stored one by one)."""
    out = []
    for offset in range(days + 1):
        day = start + timedelta(days=offset)
        for s in subjects(ws):
            for c in s.get("schedule", []):
                if meets_on(c, day):
                    out.append({
                        "id": c["id"], "kind": "academics.class_session", "area": "academics",
                        "where": f"Academics → {s['name']} → Class Schedule",
                        "title": f"{s['name']} — {c.get('title') or 'Class'}", "due_date": day.isoformat(),
                        "due_time": c.get("start", ""), "end_time": c.get("end", ""), "location": c.get("location", ""),
                        "repeating": True,
                    })
    return out


def _days_until(iso: str, today: date) -> int:
    return (date.fromisoformat(iso) - today).days


def list_today(ws: dict, today: date) -> dict:
    groups: dict[str, list[dict]] = {a: [] for a in AREAS}
    for entry in dated_entries(ws):
        if _days_until(entry["due_date"], today) <= 0:
            entry["overdue"] = _days_until(entry["due_date"], today) < 0
            groups[entry["area"]].append(entry)
    for items in groups.values():
        items.sort(key=lambda e: (e["due_date"], e.get("due_time", "")))
    return {
        "today": today.isoformat(),
        "classes_today": sorted(class_sessions(ws, today, 0), key=lambda e: e["due_time"]),
        "due_today_or_overdue": {a: v for a, v in groups.items() if v},
    }


def list_upcoming(ws: dict, today: date, days: int = 14) -> dict:
    entries = dated_entries(ws)
    for e in entries:
        e["in_days"] = _days_until(e["due_date"], today)
    entries.sort(key=lambda e: (e["due_date"], e.get("due_time", "")))
    return {
        "today": today.isoformat(),
        "overdue": [e for e in entries if e["in_days"] < 0],
        "upcoming": [e for e in entries if 0 <= e["in_days"] <= days],
        "days": days,
        "classes": class_sessions(ws, today, min(days, 21)),
        "classes_note": "Repeating classes are kept apart from deadlines, and listed for at most the next 21 days.",
    }


def list_items(ws: dict, area: str, container: str | None = None, include_done: bool = False) -> dict:
    area = to_choice(area, list(AREAS), "area")
    key: str | None = None
    if container:
        if area == "academics":
            key = find_subject(ws, container)["id"]
        elif area == "people":
            key = find_person(ws, container)["id"]
        else:
            allowed = {"life_admin": LIFE_ADMIN_LISTS, "career": CAREER_LISTS, "personal": PERSONAL_LISTS}[area]
            q = _norm(container)
            matches = [a for a in allowed if a.startswith(q) or q in a]
            if len(matches) != 1:
                raise NeedsClarification(f"Which {area.replace('_', ' ')} list?", allowed)
            key = matches[0]
    items = []
    for rec in iter_records(ws):
        if rec.area != area or (key and rec.key != key):
            continue
        if not include_done and is_done(rec):
            continue
        items.append(summarize(rec))
    return {"area": area, "container": container, "count": len(items), "items": items}


def find_items(ws: dict, query: str, area: str | None = None, include_done: bool = True, limit: int = 40) -> dict:
    q = _norm(query)
    if not q:
        raise NeedsClarification("What should I search for?")
    found = []
    for rec in iter_records(ws):
        if area and rec.area != area:
            continue
        if not include_done and is_done(rec):
            continue
        haystack = _norm(" ".join(str(v) for v in rec.item.values() if isinstance(v, (str, int, float))))
        if q in haystack:
            found.append(summarize(rec))
    return {"query": query, "count": len(found), "items": found[:limit], "truncated": len(found) > limit}


# --------------------------------------------------------------------------- adding


def _result(where: str, item: dict, dry_run: bool) -> dict:
    return {
        "dry_run": dry_run,
        "where": where,
        "item": item,
        "message": ("Would add " if dry_run else "Added ") + f"“{_title(item)}” to {where}.",
    }


def add_subject(ws: dict, name: str | None, professor: str | None = None, dry_run: bool = False) -> dict:
    name = clean(name, "subject name")
    if any(_norm(s["name"]) == _norm(name) for s in subjects(ws)):
        raise ValueError(f"A subject called '{name}' already exists.")
    item = {
        "id": new_id(), "name": name, "professor": clean(professor, "professor", required=False),
        "color": SUBJECT_COLORS[len(subjects(ws)) % len(SUBJECT_COLORS)],
        "deadlines": [], "todos": [], "milestones": [], "schedule": [],
    }
    if not dry_run:
        subjects(ws).append(item)
    return _result(f"Academics ({ws['academics']['semester']}) → new subject", item, dry_run)


def add_academic_item(ws, subject, kind, title, deadline_type=None, due_date=None, due_time=None, dry_run=False) -> dict:
    s = find_subject(ws, subject)
    kind = to_choice(kind, ["deadline", "todo", "milestone"], "kind of academic item")
    if kind == "deadline":
        item = {
            "id": new_id(), "title": clean(title, "title"),
            "type": to_choice(deadline_type, DEADLINE_TYPES, "deadline type", default="Assignment"),
            "date": to_date(due_date, "due date", required=True,
                            ask=f"When is '{title}' due? (A deadline needs a date; if it has none, should it be a to-do instead?)"),
            "time": to_time(due_time, "due time"), "status": "Not started",
        }
        target, label = s["deadlines"], "Upcoming Deadlines"
    elif kind == "todo":
        if due_date or due_time:
            raise NeedsClarification(
                "To-dos in a subject don't have dates. Should this be a deadline (with a due date) instead?",
                ["Add as a deadline", "Add as a to-do without the date"],
            )
        item = {"id": new_id(), "text": clean(title, "to-do"), "done": False}
        target, label = s["todos"], "Things To Do"
    else:
        item = {
            "id": new_id(), "title": clean(title, "milestone"),
            "date": to_date(due_date, "date", required=True, ask=f"What date is the milestone '{title}'?"), "done": False,
        }
        target, label = s["milestones"], "Major Milestones"
    if not dry_run:
        target.append(item)
    return _result(f"Academics → {s['name']} → {label}", item, dry_run)


def add_class_time(ws, subject, title=None, days=None, start_time=None, end_time=None, location=None,
                   first_day=None, last_day=None, dry_run=False) -> dict:
    """A class (or lab, or weekly meeting) that repeats every week on the same days and times."""
    s = find_subject(ws, subject)
    item = {
        "id": new_id(), "title": clean(title or "Class", "name"), "days": to_days(days),
        "start": to_time(start_time, "start time"), "end": to_time(end_time, "end time"),
        "location": clean(location, "location", required=False),
        "from": to_date(first_day, "first day"), "until": to_date(last_day, "last day"),
    }
    check_class(item)
    if not dry_run:
        s.setdefault("schedule", []).append(item)
    result = _result(f"Academics → {s['name']} → Class Schedule", item, dry_run)
    result["repeats"] = f"every {days_label(item['days'])}, {item['start']}" + (f"–{item['end']}" if item["end"] else "")
    result["note"] = "It now shows on Today and Upcoming on the days it meets."
    return result


def add_life_admin_item(ws, kind, title, due_date=None, due_time=None, status=None, link=None, notes=None,
                        recurring=None, group=None, amount=None, dry_run=False) -> dict:
    kind = to_choice(kind, ["document", "home", "grocery", "bill", "appointment"], "kind of life admin item")
    la = ws["lifeadmin"]
    if kind == "document":
        item = {
            "id": new_id(), "name": clean(title, "document name"), "deadline": to_date(due_date, "deadline"),
            "status": to_choice(status, DOC_STATUS, "status", default="Not Started"),
            "link": clean(link, "link", required=False, max_len=500), "notes": clean(notes, "notes", required=False, max_len=MAX_LONG),
        }
        target, label = la["documents"], "Documents"
    elif kind == "home":
        if due_date or due_time:
            raise NeedsClarification(
                "Home tasks don't have due dates. Should this go under Appointments & Errands (which has dates) instead?",
                ["Appointments & Errands", "Home, without the date"],
            )
        item = {"id": new_id(), "text": clean(title, "task"), "done": False,
                "recur": to_choice(recurring, RECUR, "recurrence", default="none")}
        target, label = la["home"], "Home"
    elif kind == "grocery":
        item = {"id": new_id(), "name": clean(title, "item"), "group": to_choice(group, GROCERY_GROUPS, "grocery group", default="Other"),
                "done": False}
        target, label = la["groceries"], "Groceries"
    elif kind == "bill":
        item = {
            "id": new_id(), "name": clean(title, "bill name"), "amount": to_amount(amount),
            "due": to_date(due_date, "due date", required=True, ask=f"When is the '{title}' bill due?"),
            "paid": False, "recur": to_choice(recurring, RECUR, "recurrence", default="none"),
        }
        target, label = la["bills"], "Bills & Utilities"
    else:
        item = {
            "id": new_id(), "title": clean(title, "title"),
            "date": to_date(due_date, "date", required=True, ask=f"What date is '{title}'?"),
            "time": to_time(due_time), "done": False,
        }
        target, label = la["appointments"], "Appointments & Errands"
    if not dry_run:
        target.append(item)
    return _result(f"Life Admin → {label}", item, dry_run)


def add_career_item(ws, kind, title=None, company=None, role=None, due_date=None, status=None,
                    person=None, dry_run=False) -> dict:
    kind = to_choice(kind, ["application", "task", "networking"], "kind of career item")
    cr = ws["career"]
    if kind == "application":
        item = {
            "id": new_id(), "company": clean(company, "company"), "role": clean(role, "role"),
            "deadline": to_date(due_date, "date"),
            "status": to_choice(status, APP_STATUS, "status", default="Interested"),
        }
        target, label = cr["applications"], "Applications"
    elif kind == "task":
        item = {"id": new_id(), "text": clean(title, "task"), "done": False}
        target, label = cr["tasks"], "Career Tasks"
    else:
        if due_date:
            raise NeedsClarification(
                "Networking follow-ups don't have dates. Put the date on the person's next follow-up instead, "
                "or save it as something else?",
                ["Set the person's next follow-up date", "Add without the date"],
            )
        item = {"id": new_id(), "text": clean(title, "follow-up"), "done": False,
                "personId": find_person(ws, person)["id"] if person else ""}
        target, label = cr["networking"], "Networking"
    if not dry_run:
        target.append(item)
    return _result(f"Career → {label}", item, dry_run)


def add_person(ws, name, organization=None, role=None, how_i_know_them=None, last_contacted=None,
               next_followup=None, notes=None, dry_run=False) -> dict:
    name = clean(name, "name")
    if any(_norm(p["name"]) == _norm(name) for p in ws["people"]):
        raise ValueError(f"{name} is already in People.")
    item = {
        "id": new_id(), "name": name, "org": clean(organization, "organization", required=False),
        "role": clean(role, "role", required=False), "how": clean(how_i_know_them, "how you know them", required=False),
        "last": to_date(last_contacted, "last contacted"), "next": to_date(next_followup, "next follow-up"),
        "notes": clean(notes, "notes", required=False, max_len=MAX_LONG), "tasks": [],
    }
    if not dry_run:
        ws["people"].append(item)
    return _result("People → Everyone", item, dry_run)


def add_person_task(ws, person, text, dry_run=False) -> dict:
    p = find_person(ws, person)
    item = {"id": new_id(), "text": clean(text, "task"), "done": False}
    if not dry_run:
        p["tasks"].append(item)
    return _result(f"People → {p['name']} → Linked Tasks", item, dry_run)


def add_personal_item(ws, kind, text, due_date=None, due_time=None, dry_run=False) -> dict:
    kind = to_choice(kind, ["recreation", "social", "task"], "kind of personal item")
    pr = ws["personal"]
    if kind == "task":
        if due_date or due_time:
            raise NeedsClarification(
                "Personal tasks don't have dates. Should this go under Recreation or Social, which can have a date and time?",
                ["Recreation", "Social", "Personal task without the date"],
            )
        item = {"id": new_id(), "text": clean(text, "task"), "done": False}
        target, label = pr["tasks"], "Personal Tasks"
    else:
        item = {"id": new_id(), "text": clean(text, "item"), "done": False,
                "date": to_date(due_date, "date"), "time": to_time(due_time)}
        target, label = pr["recreation" if kind == "recreation" else "social"], kind.capitalize()
    if not dry_run:
        target.append(item)
    return _result(f"Personal → {label}", item, dry_run)


# --------------------------------------------------------------------------- changing

# tool field name -> (stored key, how to validate)
EDITABLE: dict[str, dict[str, tuple[str, Any]]] = {
    "academics.subject": {"name": ("name", "text"), "professor": ("professor", "optional")},
    "academics.class": {"title": ("title", "text"), "days": ("days", "days"), "start_time": ("start", "time"),
                        "end_time": ("end", "time"), "location": ("location", "optional"),
                        "first_day": ("from", "date"), "last_day": ("until", "date")},
    "academics.deadline": {"title": ("title", "text"), "type": ("type", DEADLINE_TYPES), "status": ("status", DEADLINE_STATUS),
                           "due_date": ("date", "date"), "due_time": ("time", "time")},
    "academics.todo": {"text": ("text", "text"), "done": ("done", "bool")},
    "academics.milestone": {"title": ("title", "text"), "due_date": ("date", "date"), "done": ("done", "bool")},
    "life_admin.document": {"name": ("name", "text"), "due_date": ("deadline", "date"), "status": ("status", DOC_STATUS),
                            "link": ("link", "optional"), "notes": ("notes", "notes")},
    "life_admin.home": {"text": ("text", "text"), "recurring": ("recur", RECUR), "done": ("done", "bool")},
    "life_admin.grocery": {"name": ("name", "text"), "group": ("group", GROCERY_GROUPS), "done": ("done", "bool")},
    "life_admin.bill": {"name": ("name", "text"), "amount": ("amount", "amount"), "due_date": ("due", "date"),
                        "recurring": ("recur", RECUR), "paid": ("paid", "bool")},
    "life_admin.appointment": {"title": ("title", "text"), "due_date": ("date", "date"), "due_time": ("time", "time"),
                               "done": ("done", "bool")},
    "career.application": {"company": ("company", "text"), "role": ("role", "text"), "due_date": ("deadline", "date"),
                           "status": ("status", APP_STATUS)},
    "career.task": {"text": ("text", "text"), "done": ("done", "bool")},
    "career.networking": {"text": ("text", "text"), "done": ("done", "bool"), "person": ("personId", "person")},
    "people.person": {"name": ("name", "text"), "organization": ("org", "optional"), "role": ("role", "optional"),
                      "how_i_know_them": ("how", "optional"), "last_contacted": ("last", "date"),
                      "next_followup": ("next", "date"), "notes": ("notes", "notes")},
    "people.task": {"text": ("text", "text"), "done": ("done", "bool")},
    "personal.recreation": {"text": ("text", "text"), "due_date": ("date", "date"), "due_time": ("time", "time"),
                            "done": ("done", "bool")},
    "personal.social": {"text": ("text", "text"), "due_date": ("date", "date"), "due_time": ("time", "time"),
                        "done": ("done", "bool")},
    "personal.task": {"text": ("text", "text"), "done": ("done", "bool")},
}


def update_item(ws: dict, item_id: str, changes: dict, dry_run: bool = False) -> dict:
    rec = find_record(ws, item_id)
    fields = EDITABLE[rec.kind]
    if not changes:
        raise NeedsClarification("What should change?", sorted(fields))
    unknown = [k for k in changes if k not in fields]
    if unknown:
        raise ValueError(
            f"Can't change {', '.join(unknown)} on a {rec.kind}. Fields you can change: {', '.join(sorted(fields))}."
        )
    new_values: dict[str, Any] = {}
    for name, value in changes.items():
        key, how = fields[name]
        if how == "text":
            new_values[key] = clean(value, name)
        elif how == "optional":
            new_values[key] = clean(value, name, required=False)
        elif how == "notes":
            new_values[key] = clean(value, name, required=False, max_len=MAX_LONG)
        elif how == "date":
            new_values[key] = to_date(value, name)
        elif how == "time":
            new_values[key] = to_time(value, name)
        elif how == "bool":
            new_values[key] = to_bool(value, name)
        elif how == "amount":
            new_values[key] = to_amount(value)
        elif how == "person":
            new_values[key] = find_person(ws, value)["id"] if value else ""
        elif how == "days":
            new_values[key] = to_days(value)
        else:
            new_values[key] = to_choice(value, how, name)
    after = {**rec.item, **new_values}
    if rec.kind == "academics.class":
        check_class(after)
    if not dry_run:
        rec.item.update(new_values)
    return {
        "dry_run": dry_run, "where": rec.where, "item": summarize(rec._replace(item=after)),
        "message": ("Would update " if dry_run else "Updated ") + f"“{_title(after)}” in {rec.where}.",
    }


def complete_item(ws: dict, item_id: str, done: bool = True, dry_run: bool = False) -> dict:
    rec = find_record(ws, item_id)
    k, i = rec.kind, rec.item
    if k == "academics.deadline":
        change = {"status": "Done" if done else "Not started"}
    elif k == "life_admin.bill":
        change = {"paid": done}
    elif k == "life_admin.document":
        change = {"status": "Complete" if done else "Not Started"}
    elif k in ("academics.subject", "people.person", "career.application", "academics.class"):
        raise ValueError(f"A {k.split('.')[1]} can't be marked done. Use update_item to change its fields instead.")
    else:
        change = {"done": done}
    if not dry_run:
        i.update(change)
    word = "complete" if done else "not complete"
    return {"dry_run": dry_run, "where": rec.where, "message":
            ("Would mark " if dry_run else "Marked ") + f"“{_title(i)}” {word}."}


def delete_item(ws: dict, item_id: str, confirm: bool = False, dry_run: bool = False) -> dict:
    rec = find_record(ws, item_id)
    k, i = rec.kind, rec.item
    extra = ""
    if k == "academics.subject":
        n = len(i["deadlines"]) + len(i["todos"]) + len(i["milestones"]) + len(i.get("schedule", []))
        extra = f" and its {n} deadlines, to-dos, milestones and class times"
    elif k == "people.person":
        extra = f" and its {len(i['tasks'])} linked tasks"
    if extra and not confirm and not dry_run:
        raise NeedsClarification(
            f"Deleting “{_title(i)}” will also delete{extra}. Do you want to go ahead?",
            ["Yes, delete it", "No, keep it"],
        )
    if not dry_run:
        rec.container[:] = [x for x in rec.container if x is not i]
        if k == "people.person":
            for t in ws["career"]["networking"]:
                if t.get("personId") == i["id"]:
                    t["personId"] = ""
    return {"dry_run": dry_run, "where": rec.where, "message":
            ("Would delete " if dry_run else "Deleted ") + f"“{_title(i)}”{extra} from {rec.where}."}


def today_local() -> date:
    return date.today()
