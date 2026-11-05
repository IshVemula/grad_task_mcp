"""Marginalia's standard view of the data: the Python twin of lib/standard.js in the website repo.

The website, the morning email and Claude's tools all need to answer the same questions (what is due today? what
counts as done?). The rules live in lib/standard.js; this file is a line-for-line port, and test_standard.py checks
that it gives exactly the answers recorded in golden/expected.json (copied from the website repo). If you change one
side on purpose, regenerate the golden files there (`npm run golden`) and copy them over.

Field names are camelCase here (createdAt, spaceId...) on purpose: they match the website's, so the shape is the
same everywhere. Nothing here raises on missing or older-shaped data: absent lists count as empty.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Callable

VERSION = 2

_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_CLOCK = re.compile(r"([0-9]{1,2}):([0-9]{2})")


def is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value      # "Feb 30" is not a date
    except ValueError:
        return False


def normalize_clock(value: Any) -> str:
    match = _CLOCK.fullmatch(value.strip()) if isinstance(value, str) else None
    if not match:
        return ""
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return ""
    return f"{hour:02d}:{match.group(2)}"


def days_between(from_iso: str, to_iso: str) -> int:
    return (date.fromisoformat(to_iso) - date.fromisoformat(from_iso)).days


def weekday_of(iso: str) -> int:
    """0 = Sunday, as the website stores them."""
    return (date.fromisoformat(iso).weekday() + 1) % 7


def _list(value: Any) -> list[dict]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any) -> float | int | None:
    """JavaScript's Number(): '' and null are 0; text that isn't a number is NaN (None here)."""
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip())
    except ValueError:
        return None


# title / date / time / end: the stored field that plays that role (absent = the kind has none)
# done: {"flag"} a true/false field | {"field","values"} done when the status is one of these | {"never"}
# due_only: only counts toward Today / Upcoming while the status is one of these (applications)
# person: the field that links the item to someone in People
KINDS: dict[str, dict] = {
    "academics.space": {"area": "academics", "label": "Space", "title": "name", "done": {"never": True}},
    "academics.deadline": {"area": "academics", "label": "Deadline", "title": "title", "date": "date", "time": "time",
                           "done": {"field": "status", "values": ["Done"]}},
    "academics.milestone": {"area": "academics", "label": "Milestone", "title": "title", "date": "date", "done": {"flag": "done"}},
    "academics.todo": {"area": "academics", "label": "To-do", "title": "text", "date": "date", "time": "time",
                       "done": {"flag": "done"}, "person": "personId"},
    "academics.event": {"area": "academics", "label": "Event", "title": "title", "date": "date", "time": "time",
                        "end": "endTime", "done": {"flag": "done"}, "person": "personId"},
    "academics.class": {"area": "academics", "label": "Class time", "title": "title", "time": "start", "end": "end",
                        "done": {"never": True}, "repeating": True},
    "lifeadmin.document": {"area": "lifeadmin", "label": "Document", "title": "name", "date": "deadline",
                           "done": {"field": "status", "values": ["Complete"]}},
    "lifeadmin.home": {"area": "lifeadmin", "label": "Home task", "title": "text", "done": {"flag": "done"}},
    "lifeadmin.grocery": {"area": "lifeadmin", "label": "Grocery", "title": "name", "done": {"flag": "done"}},
    "lifeadmin.bill": {"area": "lifeadmin", "label": "Bill", "title": "name", "date": "due", "done": {"flag": "paid"}},
    "lifeadmin.appointment": {"area": "lifeadmin", "label": "Appointment", "title": "title", "date": "date", "time": "time",
                              "done": {"flag": "done"}},
    "career.application": {"area": "career", "label": "Application", "title": "company", "date": "deadline",
                           "done": {"field": "status", "values": ["Rejected", "Closed"]},
                           "due_only": {"field": "status", "values": ["Interested", "Preparing"]}},
    "career.task": {"area": "career", "label": "Career task", "title": "text", "date": "date", "time": "time",
                    "done": {"flag": "done"}, "person": "personId"},
    "career.networking": {"area": "career", "label": "Networking", "title": "text", "date": "date", "time": "time",
                          "done": {"flag": "done"}, "person": "personId"},
    "people.person": {"area": "people", "label": "Person", "title": "name", "date": "next", "done": {"never": True}},
    "people.task": {"area": "people", "label": "Person task", "title": "text", "done": {"flag": "done"}},
    "personal.recreation": {"area": "personal", "label": "Recreation", "title": "text", "date": "date", "time": "time",
                            "done": {"flag": "done"}, "person": "personId"},
    "personal.social": {"area": "personal", "label": "Social", "title": "text", "date": "date", "time": "time",
                        "done": {"flag": "done"}, "person": "personId"},
    "personal.task": {"area": "personal", "label": "Personal task", "title": "text", "done": {"flag": "done"}, "person": "personId"},
}


def for_each_raw(data: Any, cb: Callable[[str, dict, dict], None]) -> None:
    """Calls cb(kind, raw, context) for every item in the workspace, in a stable order."""
    d = data if isinstance(data, dict) else {}
    academics, life = d.get("academics") or {}, d.get("lifeadmin") or {}
    career, personal = d.get("career") or {}, d.get("personal") or {}
    for s in _list(academics.get("subjects")):
        cb("academics.space", s, {"space": s})
        for key, kind in (("deadlines", "academics.deadline"), ("todos", "academics.todo"), ("events", "academics.event"),
                          ("milestones", "academics.milestone"), ("schedule", "academics.class")):
            for x in _list(s.get(key)):
                cb(kind, x, {"space": s})
    for key, kind in (("documents", "lifeadmin.document"), ("home", "lifeadmin.home"), ("groceries", "lifeadmin.grocery"),
                      ("bills", "lifeadmin.bill"), ("appointments", "lifeadmin.appointment")):
        for x in _list(life.get(key)):
            cb(kind, x, {})
    for key, kind in (("applications", "career.application"), ("tasks", "career.task"), ("networking", "career.networking")):
        for x in _list(career.get(key)):
            cb(kind, x, {})
    for p in _list(d.get("people")):
        cb("people.person", p, {"person": p})
        for x in _list(p.get("tasks")):
            cb("people.task", x, {"person": p})
    for key, kind in (("recreation", "personal.recreation"), ("social", "personal.social"), ("tasks", "personal.task")):
        for x in _list(personal.get(key)):
            cb(kind, x, {})


def is_done(kind: str, raw: dict) -> bool:
    rule = KINDS[kind]["done"]
    if rule.get("never"):
        return False
    if "flag" in rule:
        return bool(raw.get(rule["flag"]))
    return raw.get(rule["field"]) in rule["values"]


def set_done(kind: str, raw: dict, done: bool) -> bool:
    """Mark an item finished (or reopen it). False when that kind has no "finished" (a space, person, application, class time)."""
    rule = KINDS[kind]["done"]
    if rule.get("never") or kind == "career.application":
        return False
    if "flag" in rule:
        raw[rule["flag"]] = bool(done)
    elif kind == "academics.deadline":
        raw["status"] = "Done" if done else "Not started"
    elif kind == "lifeadmin.document":
        raw["status"] = "Complete" if done else "Not Started"
    return True


def standard_items(data: Any, today: str = "") -> list[dict]:
    today = today if is_iso_date(today) else ""
    people = {p["id"]: _str(p.get("name")) for p in _list(data.get("people") if isinstance(data, dict) else None) if p.get("id")}
    out: list[dict] = []

    def visit(kind: str, raw: dict, ctx: dict) -> None:
        spec = KINDS[kind]
        space = ctx.get("space")
        raw_date = raw.get(spec["date"]) if spec.get("date") else ""
        day = raw_date if is_iso_date(raw_date) else ""
        item: dict[str, Any] = {
            "id": _str(raw.get("id")), "kind": kind, "area": spec["area"], "label": spec["label"],
            "spaceId": _str(space.get("id")) if space is not None else "",
            "spaceName": _str(space.get("name")) if space is not None else "",
            "title": _str(raw.get(spec["title"])), "notes": _str(raw.get("notes")),
            "date": day,
            "time": normalize_clock(raw.get(spec["time"])) if spec.get("time") else "",
            "endTime": normalize_clock(raw.get(spec["end"])) if spec.get("end") else "",
            "done": is_done(kind, raw), "status": _str(raw.get("status")),
            "createdAt": _str(raw.get("createdAt")), "updatedAt": _str(raw.get("updatedAt")), "doneAt": _str(raw.get("doneAt")),
            "personId": _str(raw.get(spec["person"])) if spec.get("person") else "", "personName": "",
            "dueCounts": False, "daysUntil": None,
        }
        if item["personId"]:
            item["personName"] = people.get(item["personId"]) or ""
        counts = bool(day) and not item["done"] and not spec.get("repeating")
        if counts and spec.get("due_only"):
            counts = raw.get(spec["due_only"]["field"]) in spec["due_only"]["values"]
        item["dueCounts"] = counts
        if today and day:
            item["daysUntil"] = days_between(today, day)

        shown = item["title"] or ("" if space is not None else spec["label"])
        if space is not None and kind not in ("academics.space", "academics.class"):
            shown = (item["spaceName"] or "Untitled space") + " — " + (item["title"] or spec["label"])
        elif kind == "people.person":
            shown = "Follow up: " + (item["title"] or "someone")
        elif kind == "career.application":
            shown = (item["title"] or "Application") + (" — " + _str(raw.get("role")) if _str(raw.get("role")) else "")
        if item["personName"] and spec.get("person"):
            shown += " — " + item["personName"]
        item["dueTitle"] = shown

        extra: dict[str, Any] = {}
        if kind == "lifeadmin.bill":
            extra["amount"], extra["recur"] = _number(raw.get("amount")), _str(raw.get("recur"))
        if kind == "academics.deadline":
            extra["type"] = _str(raw.get("type"))
        if kind == "career.application":
            extra["role"], extra["applied"] = _str(raw.get("role")), _str(raw.get("applied"))
        if kind == "academics.event":
            extra["location"] = _str(raw.get("location"))
        item["extra"] = extra
        item["raw"] = raw
        out.append(item)

    for_each_raw(data, visit)
    return out


def meets_on(cls: dict, iso: str) -> bool:
    """Does this class time meet on `iso`? (right weekday, within its first and last day)"""
    days = cls.get("days")
    if not is_iso_date(iso) or not isinstance(days, list) or weekday_of(iso) not in days:
        return False
    if is_iso_date(cls.get("from")) and iso < cls["from"]:
        return False
    if is_iso_date(cls.get("until")) and iso > cls["until"]:
        return False
    return True


def class_sessions_on(data: Any, iso: str) -> list[dict]:
    """Repeating class times that meet on `iso`, earliest first."""
    out: list[dict] = []
    if not is_iso_date(iso):
        return out

    def visit(kind: str, raw: dict, ctx: dict) -> None:
        if kind != "academics.class":
            return
        start = normalize_clock(raw.get("start"))
        if not start or not meets_on(raw, iso):
            return
        space = ctx["space"]
        out.append({
            "date": iso, "start": start, "end": normalize_clock(raw.get("end")), "title": _str(raw.get("title")),
            "location": _str(raw.get("location")), "spaceId": _str(space.get("id")),
            "spaceName": _str(space.get("name")) or "Untitled space", "color": _str(space.get("color")),
            "classId": _str(raw.get("id")),
        })

    for_each_raw(data, visit)
    out.sort(key=lambda s: (s["start"], s["spaceName"].casefold()))
    return out


# ---- tracking: when an item was created, last changed, and finished ----
_STAMPS = ("createdAt", "updatedAt", "doneAt")
_CHILD_LISTS = ("deadlines", "todos", "events", "milestones", "schedule", "tasks")      # a space's / person's own items


def _signature(raw: dict) -> str:
    keys = sorted(k for k in raw if k not in _STAMPS and k not in _CHILD_LISTS)
    return json.dumps([[k, raw[k]] for k in keys], sort_keys=True, ensure_ascii=False)


def snapshot(data: Any) -> dict:
    before: dict[str, dict] = {}

    def visit(kind: str, raw: dict, ctx: dict) -> None:
        if raw.get("id"):
            before[raw["id"]] = {"sig": _signature(raw), "done": is_done(kind, raw)}

    for_each_raw(data, visit)
    return before


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def stamp(data: Any, before: dict, now: str | None = None) -> int:
    """Give anything new a createdAt, anything edited an updatedAt, and set / clear doneAt when finished / reopened."""
    now = now or now_iso()
    touched = [0]

    def visit(kind: str, raw: dict, ctx: dict) -> None:
        if not raw.get("id"):
            return
        was, done = before.get(raw["id"]), is_done(kind, raw)
        if was is None:
            raw["createdAt"] = raw.get("createdAt") or now
            raw["updatedAt"] = now
            raw["doneAt"] = now if done else (raw.get("doneAt") or "")
            touched[0] += 1
        elif was["sig"] != _signature(raw):
            raw["updatedAt"] = now
            if done and not was["done"]:
                raw["doneAt"] = now
            if not done and was["done"]:
                raw["doneAt"] = ""
            touched[0] += 1

    for_each_raw(data, visit)
    return touched[0]


def migrate(data: Any) -> bool:
    """v1 -> v2: a space (was "subject") gets a type, a contact (was "professor") and a list of events.
    Nothing is removed; running it again changes nothing. Returns True if it changed anything."""
    if not isinstance(data, dict):
        return False
    changed = False
    for s in _list((data.get("academics") or {}).get("subjects")):
        if not isinstance(s.get("events"), list):
            s["events"] = []
            changed = True
        if "contact" not in s:
            s["contact"] = _str(s.get("professor"))
            changed = True
        if "professor" in s:
            del s["professor"]
            changed = True
        if "type" not in s:
            s["type"] = "Course" if _list(s.get("schedule")) else ""
            changed = True
    if data.get("schemaVersion") != VERSION:
        data["schemaVersion"] = VERSION
        changed = True
    return changed
