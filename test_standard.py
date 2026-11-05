"""The Python port must give exactly the answers the website's standard view gives (golden/expected.json)."""

import copy
import json
from pathlib import Path

import pytest

import standard

GOLDEN = Path(__file__).parent / "golden"


def read(name):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


EXPECTED = read("expected.json")
SESSION_DATES = ["2026-11-05", "2026-11-06", "2026-11-10"]


def test_standard_items_match_the_website():
    items = [{k: v for k, v in i.items() if k != "raw"} for i in standard.standard_items(read("workspace.json"), EXPECTED["today"])]
    assert items == EXPECTED["items"]


def test_class_sessions_match_the_website():
    ws = read("workspace.json")
    assert {d: standard.class_sessions_on(ws, d) for d in SESSION_DATES} == EXPECTED["sessions"]


def test_stamping_matches_the_website():
    ws, ops = read("workspace.json"), read("stamp-ops.json")
    before = standard.snapshot(ws)
    for kind, raw, _ in _walk(ws):
        if raw["id"] in ops["edit"]:
            raw.update(ops["edit"][raw["id"]])
        if raw["id"] in ops["done"]:
            standard.set_done(kind, raw, ops["done"][raw["id"]])
    for add in ops["add"]:
        space = next(s for s in ws["academics"]["subjects"] if s["id"] == add["space"])
        space.setdefault(add["list"], []).append(copy.deepcopy(add["item"]))
    touched = standard.stamp(ws, before, ops["now"])
    by_id = {}
    for _, raw, _ in _walk(ws):
        if raw.get("createdAt") or raw.get("updatedAt") or raw.get("doneAt"):
            by_id[raw["id"]] = {"createdAt": raw.get("createdAt") or "", "updatedAt": raw.get("updatedAt") or "",
                                "doneAt": raw.get("doneAt") or ""}
    assert {"touched": touched, "byId": by_id} == EXPECTED["stamps"]


def test_migration_matches_the_website_and_is_idempotent():
    ws = read("workspace-v1.json")
    assert standard.migrate(ws) is True
    assert ws == EXPECTED["migrated"]
    assert standard.migrate(ws) is False


def test_garbage_in_does_not_raise():
    for junk in (None, {}, [], "x", {"academics": {"subjects": [None, 3, {"deadlines": "nope"}]}, "people": [None]}):
        standard.standard_items(junk, "2026-11-05")
        standard.class_sessions_on(junk, "2026-11-05")
        standard.stamp(junk, standard.snapshot(junk))
        standard.migrate(junk)


@pytest.mark.parametrize("value,ok", [("2026-02-30", False), ("2026-02-28", True), ("２０２６-02-28", False), ("2026-02-28\n", False)])
def test_dates_are_strict(value, ok):
    assert standard.is_iso_date(value) is ok


def _walk(ws):
    found = []
    standard.for_each_raw(ws, lambda k, r, c: found.append((k, r, c)))
    return found
