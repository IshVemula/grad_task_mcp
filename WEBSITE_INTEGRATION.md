# Connecting Claude to your Marginalia website

The MCP server now reads and writes the same data you see on your Marginalia website, instead of
a separate local task list. Ask Claude to add a deadline, a bill, or a follow-up, and it shows up
on the site; edit something on the site and Claude sees it.

## Setup

1. **Update the database once.** In Supabase: SQL Editor, paste `supabase/002_add_rev.sql` from the
   Marginalia repo, Run. (It adds a version number so the website and Claude never overwrite each other.)
2. **Deploy the matching website update** (push the Marginalia repo; Vercel redeploys), then open the
   site once and sign in so your workspace exists.
3. **Fill in `.env`** in this folder: `SUPABASE_EMAIL` and `SUPABASE_PASSWORD` are the email and password
   you sign in to the website with. The URL and anon key are already there. `.env` is gitignored and set
   to owner-only permissions (`chmod 600`). Never use the `service_role` key.
4. **Restart Claude Desktop** so it reloads the server. The tools change names; the old
   `add_task` / `list_tasks` / `update_task` / `delete_task` are replaced by the ones below.

No new Python packages are needed.

## Where things go

You decide. Tell Claude the destination ("add a quiz for Decision Framing on Nov 3", "put it under Social").
Claude is instructed never to guess, and the tools refuse to save when something is missing or doesn't fit.
In that case they return a question instead, Claude asks you, and **nothing is saved until you answer**.

Examples that make Claude ask first:

- A subject, person, or list that doesn't exist yet ("Which subject? Or should I create it?")
- A deadline with no date, a bill with no amount
- A date on something that can't have one (a to-do, a home chore, a personal task)
- Things the website has no place for: recurring class sessions, calendar events, meetings

Add `dry_run` to any add/change tool to preview exactly where something would land without saving.

## Tools

| Read | Add | Change |
|---|---|---|
| `get_workspace_overview` | `add_subject` | `update_item` |
| `list_today` | `add_academic_item` (deadline / to-do / milestone) | `complete_item` |
| `list_upcoming` | `add_life_admin_item` (document / home / grocery / bill / appointment) | `delete_item` |
| `list_items` | `add_career_item` (application / task / networking) | |
| `find_items` | `add_person`, `add_person_task`, `add_personal_item` | |

Deleting a subject or a person also deletes what's inside it, so `delete_item` asks for confirmation first.

## How it stays in sync with the site

Both sides save with a version number. If the website saved while Claude was working, Claude re-reads
the newest data and redoes its change on top, so neither overwrites the other. The website merges
changes made elsewhere item by item and refreshes itself every ~20 seconds while the tab is open.

## Troubleshooting

| Message | Fix |
|---|---|
| "Missing settings in the MCP server's .env" | Fill in `SUPABASE_EMAIL` / `SUPABASE_PASSWORD`, restart Claude |
| "Supabase rejected SUPABASE_EMAIL / SUPABASE_PASSWORD" | Use the exact email/password you sign in to the site with |
| "Your database needs a one-time update" | Run `supabase/002_add_rev.sql` (step 1) |
| "No workspace exists yet" | Open the website once and sign in |

## Tests

```bash
.venv/bin/python -m pytest -q
```

`test_workspace.py` covers placement and the ask-first rules, `test_supabase_client.py` covers sign-in and
versioned saves against a fake Supabase (including the website saving mid-way), and
`test_server_tools.py` calls the real tools end to end.
