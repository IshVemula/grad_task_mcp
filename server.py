from datetime import date
from typing import Annotated, Literal

from pydantic import Field

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

import workspace as ws_ops
from config import APP_NAME, setting
from security import check_rate_limit
from supabase_client import WorkspaceClient, WorkspaceError
from workspace import NeedsClarification


INSTRUCTIONS = """
These tools read and change the user's Marginalia website: their personal planner for graduate school.
It has five areas, and every item lives in one specific list:

- Academics: subjects (grouped by semester). Each subject has Upcoming Deadlines (dated: assignment, exam,
  project, presentation, reading, quiz), Class Schedule (classes, labs or meetings that repeat weekly on set
  days and times), Things To Do (optional date and time), and Major Milestones (dated).
- Life Admin: Documents, Home tasks, Groceries, Bills & Utilities, Appointments & Errands.
- Career: Applications (one date), Career Tasks and Networking follow-ups/events (both can have a date and time).
- People: a lightweight contact list; each person has linked tasks and follow-up dates.
- Personal: Recreation, Social, Personal Tasks.

RULES FOR PLACING THINGS
1. The user decides where things go. Use the destination they named. Never guess an area, subject, person,
   or list. If they did not say, or you are not sure, ask them BEFORE calling any add tool.
2. If something does not fit any list above (for example one-off calendar events, meetings that aren't
   weekly, or anything that repeats less often than weekly), do not force it into the closest list. Tell the
   user it has no natural home on the site and ask where they want it. Weekly classes, labs and meetings
   belong in a subject's Class Schedule: use add_class_time, not a deadline.
3. If a tool returns needs_clarification, nothing was saved. Ask the user its question, wait for the
   answer, and only then try again.
4. Call get_workspace_overview first if you need the real subject and people names. Use dry_run=true to
   preview exactly where something will land when the placement is not obvious.
5. Report where each item landed using the "where" field in the result.
6. Never delete or overwrite anything the user did not ask you to. Ask before deleting subjects or people.
""".strip()

mcp = MCPServer(APP_NAME, instructions=INSTRUCTIONS)

WRITE_LIMIT_PER_MINUTE = 30

_client: WorkspaceClient | None = None


def client() -> WorkspaceClient:
    global _client
    if _client is None:
        _client = WorkspaceClient(
            setting("SUPABASE_URL"),
            setting("SUPABASE_ANON_KEY"),
            setting("SUPABASE_EMAIL"),
            setting("SUPABASE_PASSWORD"),
        )
    return _client


def _guard(run) -> dict:
    try:
        return run()
    except NeedsClarification as ask:
        return ask.as_response()
    except (ValueError, WorkspaceError) as error:
        return {"success": False, "error": str(error)}


def _read(op) -> dict:
    return _guard(lambda: {"success": True, **op(client().snapshot())})


def _write(op, dry_run: bool) -> dict:
    def run() -> dict:
        if not dry_run:
            check_rate_limit(limit=WRITE_LIMIT_PER_MINUTE)

        def change(workspace: dict) -> tuple[dict, bool]:
            return op(workspace), not dry_run

        return {"success": True, **client().update(change)}

    return _guard(run)


Subject = Annotated[str, Field(description="Subject name (or id). Must be a subject that already exists.")]
Title = Annotated[str, Field(min_length=1, max_length=200, description="Title or name of the item.")]
DueDate = Annotated[date | None, Field(description="Calendar date, YYYY-MM-DD.")]
DueTime = Annotated[str | None, Field(description="Time of day, like 14:30 or 2:30 PM.")]
DryRun = Annotated[bool, Field(description="If true, nothing is saved; shows where the item would go.")]
ItemId = Annotated[str, Field(description="The id of an item, taken from list_items or find_items. Never invent one.")]

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
ADDS = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)
EDITS = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
DELETES = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False)


# ----------------------------------------------------------------------- reading


@mcp.tool(
    title="Workspace Overview",
    description=(
        "See the user's real subjects, people, list sizes, allowed values, and what the website does NOT "
        "support. Call this before adding anything so you use real names."
    ),
    annotations=READ_ONLY,
)
def get_workspace_overview() -> dict:
    return _read(lambda w: ws_ops.overview(w, ws_ops.today_local()))


@mcp.tool(
    title="List Today",
    description="Everything due today or overdue, grouped by area (what the website's Today page shows).",
    annotations=READ_ONLY,
)
def list_today() -> dict:
    return _read(lambda w: ws_ops.list_today(w, ws_ops.today_local()))


@mcp.tool(
    title="List Upcoming",
    description="Everything with a date coming up in the next N days, plus anything overdue.",
    annotations=READ_ONLY,
)
def list_upcoming(
    days: Annotated[int, Field(ge=1, le=365, description="How many days ahead to look.")] = 14,
) -> dict:
    return _read(lambda w: ws_ops.list_upcoming(w, ws_ops.today_local(), days))


@mcp.tool(
    title="List Items",
    description=(
        "List the items in one area, optionally narrowed to one list. container: a subject name (academics), "
        "a person's name (people), or a list such as documents, home, groceries, bills, appointments "
        "(life_admin); applications, tasks, networking (career); recreation, social, tasks (personal)."
    ),
    annotations=READ_ONLY,
)
def list_items(
    area: Annotated[Literal["academics", "life_admin", "career", "people", "personal"], Field(description="Which area.")],
    container: Annotated[str | None, Field(description="Optional subject, person, or list to narrow to.")] = None,
    include_done: Annotated[bool, Field(description="Include completed items.")] = False,
) -> dict:
    return _read(lambda w: ws_ops.list_items(w, area, container, include_done))


@mcp.tool(
    title="Find Items",
    description="Search every list by text. Use this to get an item's id before changing or deleting it.",
    annotations=READ_ONLY,
)
def find_items(
    query: Annotated[str, Field(min_length=1, description="Text to look for.")],
    area: Annotated[Literal["academics", "life_admin", "career", "people", "personal"] | None,
                    Field(description="Optional area to search within.")] = None,
) -> dict:
    return _read(lambda w: ws_ops.find_items(w, query, area))


# ----------------------------------------------------------------------- adding


@mcp.tool(
    title="Add Subject",
    description=(
        "Create a new subject in the current semester. Only do this when the user has asked for a new subject."
    ),
    annotations=ADDS,
)
def add_subject(
    name: Title,
    professor: Annotated[str | None, Field(description="Optional professor name.")] = None,
    dry_run: DryRun = False,
) -> dict:
    return _write(lambda w: ws_ops.add_subject(w, name, professor, dry_run), dry_run)


@mcp.tool(
    title="Add Academic Item",
    description=(
        "Add to ONE existing subject: a deadline (needs a due date; types: Assignment, Exam, Project, "
        "Presentation, Reading, Quiz), a to-do (optional date and time; dated to-dos show on Today and Upcoming), or a milestone (needs a date). The user must have "
        "said which subject; if the subject doesn't exist yet this asks instead of creating it."
    ),
    annotations=ADDS,
)
def add_academic_item(
    subject: Subject,
    kind: Annotated[Literal["deadline", "todo", "milestone"], Field(description="What kind of item.")],
    title: Title,
    deadline_type: Annotated[
        Literal["Assignment", "Exam", "Project", "Presentation", "Reading", "Quiz"] | None,
        Field(description="For deadlines. Defaults to Assignment."),
    ] = None,
    due_date: DueDate = None,
    due_time: DueTime = None,
    dry_run: DryRun = False,
) -> dict:
    return _write(
        lambda w: ws_ops.add_academic_item(w, subject, kind, title, deadline_type, due_date, due_time, dry_run), dry_run
    )


@mcp.tool(
    title="Add Class Time",
    description=(
        "Add a class, lab, or meeting that repeats WEEKLY to ONE existing subject's Class Schedule: the days it "
        "meets and a start time (end time and location optional; optional first and last day to bound it). It "
        "then shows on Today and Upcoming on the days it meets, so do not also add each session as a deadline. "
        "The user must have said which subject and when it meets; if not, this asks."
    ),
    annotations=ADDS,
)
def add_class_time(
    subject: Subject,
    days: Annotated[list[Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]],
                    Field(min_length=1, description="Days of the week it meets, e.g. ['Tue', 'Thu'].")],
    start_time: Annotated[str, Field(description="Start time, like 08:40 or 8:40 AM.")],
    end_time: Annotated[str | None, Field(description="End time, like 09:55 or 9:55 AM.")] = None,
    title: Annotated[str | None, Field(max_length=200, description="e.g. Lecture, Lab, Capstone meeting. Defaults to Class.")] = None,
    location: Annotated[str | None, Field(max_length=200, description="e.g. Room 120.")] = None,
    first_day: Annotated[date | None, Field(description="Optional: first date it meets, YYYY-MM-DD.")] = None,
    last_day: Annotated[date | None, Field(description="Optional: last date it meets, YYYY-MM-DD.")] = None,
    dry_run: DryRun = False,
) -> dict:
    return _write(
        lambda w: ws_ops.add_class_time(w, subject, title, days, start_time, end_time, location, first_day, last_day, dry_run),
        dry_run,
    )


@mcp.tool(
    title="Add Life Admin Item",
    description=(
        "Add to Life Admin. kind=document (deadline, status, link, notes), home (a chore; no date; may recur), "
        "grocery (item; optional group Produce/Dairy/Pantry/Household), bill (needs amount and due date), "
        "appointment (needs a date; optional time). Home chores and groceries cannot have due dates."
    ),
    annotations=ADDS,
)
def add_life_admin_item(
    kind: Annotated[Literal["document", "home", "grocery", "bill", "appointment"], Field(description="Which list.")],
    title: Title,
    due_date: DueDate = None,
    due_time: DueTime = None,
    amount: Annotated[float | None, Field(ge=0, description="Bills only: amount in dollars.")] = None,
    recurring: Annotated[Literal["none", "daily", "weekly", "monthly"] | None,
                         Field(description="Home tasks and bills.")] = None,
    group: Annotated[Literal["Produce", "Dairy", "Pantry", "Household", "Other"] | None,
                     Field(description="Groceries only.")] = None,
    status: Annotated[Literal["Not Started", "In Progress", "Submitted", "Waiting", "Complete"] | None,
                      Field(description="Documents only.")] = None,
    link: Annotated[str | None, Field(max_length=500, description="Documents only.")] = None,
    notes: Annotated[str | None, Field(max_length=2000, description="Documents only.")] = None,
    dry_run: DryRun = False,
) -> dict:
    return _write(
        lambda w: ws_ops.add_life_admin_item(
            w, kind, title, due_date, due_time, status, link, notes, recurring, group, amount, dry_run
        ),
        dry_run,
    )


@mcp.tool(
    title="Add Career Item",
    description=(
        "Add to Career. kind=application (company and role; ONE optional date and no time: the deadline while the "
        "status is Interested or Preparing, or the day applied once it is Applied or later; status Interested/"
        "Preparing/Applied/Interview/Waiting/Offer/Rejected/Closed), task (a to-do; optional date and time), or "
        "networking (a reach-out or event such as a coffee chat or career fair; optional date and time; optionally "
        "linked to someone already in People)."
    ),
    annotations=ADDS,
)
def add_career_item(
    kind: Annotated[Literal["application", "task", "networking"], Field(description="Which list.")],
    title: Annotated[str | None, Field(max_length=200, description="Task or follow-up text (task, networking).")] = None,
    company: Annotated[str | None, Field(max_length=200, description="Applications only.")] = None,
    role: Annotated[str | None, Field(max_length=200, description="Applications only.")] = None,
    due_date: Annotated[date | None, Field(description="Optional date, YYYY-MM-DD. For applications it is the single date.")] = None,
    due_time: Annotated[str | None, Field(description="Optional time like 14:30 or 2:30 PM (tasks and networking only; needs a date).")] = None,
    status: Annotated[
        Literal["Interested", "Preparing", "Applied", "Interview", "Waiting", "Offer", "Rejected", "Closed"] | None,
        Field(description="Applications only. Defaults to Interested."),
    ] = None,
    person: Annotated[str | None, Field(description="Networking only: an existing person to link.")] = None,
    dry_run: DryRun = False,
) -> dict:
    return _write(
        lambda w: ws_ops.add_career_item(w, kind, title, company, role, due_date, status, person, dry_run, due_time=due_time),
        dry_run,
    )


@mcp.tool(
    title="Add Person",
    description="Add someone to People. Only when the user asks for a new person.",
    annotations=ADDS,
)
def add_person(
    name: Title,
    organization: Annotated[str | None, Field(max_length=200)] = None,
    role: Annotated[str | None, Field(max_length=200)] = None,
    how_i_know_them: Annotated[str | None, Field(max_length=200, description="e.g. Classmate, Recruiter, Mentor.")] = None,
    last_contacted: Annotated[date | None, Field(description="YYYY-MM-DD.")] = None,
    next_followup: Annotated[date | None, Field(description="YYYY-MM-DD.")] = None,
    notes: Annotated[str | None, Field(max_length=2000)] = None,
    dry_run: DryRun = False,
) -> dict:
    return _write(
        lambda w: ws_ops.add_person(w, name, organization, role, how_i_know_them, last_contacted, next_followup, notes, dry_run),
        dry_run,
    )


@mcp.tool(
    title="Add Person Task",
    description="Add a task to ONE existing person's profile (e.g. 'send grant requirements').",
    annotations=ADDS,
)
def add_person_task(
    person: Annotated[str, Field(description="Name (or id) of someone already in People.")],
    text: Title,
    dry_run: DryRun = False,
) -> dict:
    return _write(lambda w: ws_ops.add_person_task(w, person, text, dry_run), dry_run)


@mcp.tool(
    title="Add Personal Item",
    description=(
        "Add to Personal. kind=recreation or social (a thing to make time for; optional date and time), or "
        "task (undated). Personal tasks cannot have dates."
    ),
    annotations=ADDS,
)
def add_personal_item(
    kind: Annotated[Literal["recreation", "social", "task"], Field(description="Which list.")],
    text: Title,
    due_date: DueDate = None,
    due_time: DueTime = None,
    dry_run: DryRun = False,
) -> dict:
    return _write(lambda w: ws_ops.add_personal_item(w, kind, text, due_date, due_time, dry_run), dry_run)


# ----------------------------------------------------------------------- changing


@mcp.tool(
    title="Update Item",
    description=(
        "Change fields on an existing item, found by id (use find_items or list_items first). Field names: "
        "title/text/name, due_date, due_time, status, type, notes, link, amount, recurring, group, role, "
        "company, organization, how_i_know_them, last_contacted, next_followup, person, done, "
        "paid; for class times: days (e.g. [\"Tue\", \"Thu\"]), start_time, end_time, location, first_day, last_day. Use an empty string to clear a date or text field. Only fields that exist on that kind of "
        "item are accepted."
    ),
    annotations=EDITS,
)
def update_item(
    item_id: ItemId,
    changes: Annotated[dict[str, str | int | float | bool | list[str] | None], Field(description="Field names and their new values.")],
    dry_run: DryRun = False,
) -> dict:
    return _write(lambda w: ws_ops.update_item(w, item_id, changes, dry_run), dry_run)


@mcp.tool(
    title="Complete Item",
    description=(
        "Mark an item done (a to-do, deadline, milestone, appointment) or paid (a bill) or complete (a "
        "document). Set done=false to reopen it."
    ),
    annotations=EDITS,
)
def complete_item(
    item_id: ItemId,
    done: Annotated[bool, Field(description="True to complete, false to reopen.")] = True,
    dry_run: DryRun = False,
) -> dict:
    return _write(lambda w: ws_ops.complete_item(w, item_id, done, dry_run), dry_run)


@mcp.tool(
    title="Delete Item",
    description=(
        "Permanently delete one item by id. Deleting a subject or a person also deletes everything inside "
        "it, so it asks for confirmation first. Only delete what the user asked you to delete."
    ),
    annotations=DELETES,
)
def delete_item(
    item_id: ItemId,
    confirm: Annotated[bool, Field(description="Set true only after the user has agreed to delete a subject or person.")] = False,
    dry_run: DryRun = False,
) -> dict:
    return _write(lambda w: ws_ops.delete_item(w, item_id, confirm, dry_run), dry_run)


# ----------------------------------------------------------------------- prompts


@mcp.prompt(
    title="Plan My Day",
    description=(
        "Create reusable instructions for organizing "
        "a graduate student's daily tasks."
    ),
)
def plan_my_day(
    priority: Annotated[
        Literal[
            "balanced",
            "deadlines",
            "academic",
            "personal",
        ],
        Field(
            description=(
                "The main priority to use when "
                "organizing the day."
            ),
        ),
    ] = "balanced",
) -> str:
    """
    Create instructions for planning a student's day.
    """

    return f"""
You are helping a graduate student plan their day.

First call list_today and list_upcoming to see what is due, then build a realistic plan.

Planning priority: {priority}

Follow these rules:

1. Prioritize tasks with upcoming deadlines.
2. Group similar tasks where practical.
3. Do not schedule every minute of the day.
4. Include reasonable breaks.
5. Separate academic work, career, life admin, and personal responsibilities.
6. Clearly identify the three most important tasks.
7. If there are too many tasks for one day, recommend what should move to another day.
8. Do not change anything on the website unless the user asks you to.
"""


# stdio server launch pattern adapted from the official MCP Python SDK:
# https://github.com/modelcontextprotocol/python-sdk
if __name__ == "__main__":
    mcp.run()
