# Grad Student Task Manager (MCP Server)

A small [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that lets an AI assistant (like Claude Desktop) read and add items to a graduate student's task list. It was built as a learning project to demonstrate a working MCP server *and* to explore two common web-app security concerns — SQL injection and rate limiting — in an MCP context.

This README assumes you've never used MCP before and walks through the concepts as well as the setup.

## Table of contents

- [Project overview](#project-overview)
- [MCP architecture, explained](#mcp-architecture-explained)
- [Tools and prompt](#tools-and-prompt)
- [Prerequisites](#prerequisites)
- [Installation and setup with uv](#installation-and-setup-with-uv)
- [Running the MCP Inspector](#running-the-mcp-inspector)
- [Connecting to Claude Desktop](#connecting-to-claude-desktop)
- [Example tool calls](#example-tool-calls)
- [Input sanitization](#input-sanitization)
- [SQL injection exploit demonstration](#sql-injection-exploit-demonstration)
- [Rate limiting](#rate-limiting)
- [Rate-limit exploit demonstration](#rate-limit-exploit-demonstration)
- [Why authentication is not required](#why-authentication-is-not-required)
- [Project limitations](#project-limitations)
- [Repository structure](#repository-structure)

## Project overview

Graduate students juggle a mix of task types — problem sets, advisor meetings, forms, career-fair prep, and everything in between. This project is a tiny task manager, exposed as an **MCP server**, so that an AI assistant can add tasks and list them on the student's behalf, in plain conversation, instead of the student switching to a separate to-do app.

Concretely, the server:

- stores tasks (title, category, optional due date) in a local SQLite database,
- exposes two **tools** an AI client can call — `add_task` and `list_tasks` — and
- exposes one **prompt** — `plan_my_day` — that asks the assistant to turn the current task list into a daily plan.

Because the server accepts free-text input from a student (relayed through an AI model, which itself is relaying whatever the student typed), it's a good small case study for input handling: what happens if someone's "task title" is actually an attempted SQL injection string, and what stops a client from hammering the server with requests. Both are covered below, with working demonstrations.

## MCP architecture, explained

If you've never touched MCP before, the mental model is closer to "a very small, structured API for AI assistants" than anything exotic.

**The three roles:**

- **Host** — the AI application the person is actually using. In this project, that's Claude Desktop.
- **Client** — the piece inside the host that speaks the MCP protocol and manages a 1:1 connection to a server. Claude Desktop creates one client per configured server.
- **Server** — the program that exposes capabilities (in our case, `server.py`, running as its own local process). A server doesn't know or care which AI model is on the other end; it just answers requests.

**How they talk:** the client and server exchange JSON-RPC 2.0 messages. This project uses the **stdio transport**, which means Claude Desktop literally starts `server.py` as a child process and talks to it over that process's standard input/output — no network socket, no port, no URL. (MCP also supports an HTTP-based transport for servers that live elsewhere on a network, but this project doesn't use it.)

```
┌─────────────────────┐        JSON-RPC over stdio       ┌───────────────────────┐
│   Claude Desktop     │  ───────────────────────────▶   │   grad-task-mcp        │
│   (host + MCP client)│  ◀───────────────────────────   │   server.py (server)   │
└─────────────────────┘                                   └───────────┬───────────┘
                                                                        │
                                                                        ▼
                                                                 tasks.db (SQLite)
```

**What a server can expose**, per the spec:

- **Tools** — functions the model can *call* to take an action or fetch data (here: `add_task`, `list_tasks`). The model decides when to call them based on the conversation.
- **Resources** — data the client can read, more like a file or API response than an action (this project doesn't define any).
- **Prompts** — reusable, parameterized prompt templates the *user* can invoke on demand (here: `plan_my_day`).

When Claude Desktop connects to this server, it asks "what tools/prompts do you have?", the server answers with their names, descriptions, and input schemas (auto-generated from the Python function signatures and docstrings), and from then on Claude can call `add_task` or `list_tasks` mid-conversation whenever it decides that's the right thing to do.

## Tools and prompt

### `add_task(title: str, category: str, due_date: str | None = None) -> dict`

Adds a new task.

- `title` — free text, required.
- `category` — must be one of: `academic`, `meeting`, `life_admin`, `recreational`, `people`, `other`.
- `due_date` — optional, must be `YYYY-MM-DD` if provided.

Returns `{"success": true, "task_id": <int>, "message": "..."}` on success, or `{"success": false, "error": "..."}` if validation fails.

### `list_tasks(category: str | None = None) -> dict`

Lists all *incomplete* tasks, soonest due date first (tasks with no due date sort last). Pass `category` to filter to one category.

Returns `{"success": true, "count": <int>, "tasks": [...]}`.

### Prompt: `plan_my_day(priority: str = "balanced") -> str`

Not a tool — this is a **prompt template** the user (not the model) invokes, typically from a "/" command or prompt picker in the client UI. It doesn't touch the database itself; it returns a block of instructions telling the assistant how to turn the student's tasks into a realistic daily plan (prioritize deadlines, group similar tasks, include breaks, call out the top three priorities, etc.), with `priority` letting the user nudge the tone (e.g. `"deadline-focused"` vs `"balanced"`).

## Prerequisites

- **Python 3.12+** (pinned via `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** — used for dependency management and running the project. Install it with:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  or see the [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for other platforms.
- **Claude Desktop** (or another MCP-compatible host), if you want to connect the server to an assistant rather than just testing it standalone.
- **Node.js/npx**, only if you plan to run the standalone MCP Inspector via `npx` (see below).

## Installation and setup with uv

From the project root:

```bash
# 1. Clone or open the project
cd grad-task-mcp

# 2. Let uv create a virtual environment and install dependencies
#    from pyproject.toml / uv.lock
uv sync

# 3. (Optional) confirm it installed correctly
uv run python -c "import mcp; print('mcp package OK')"
```

`uv sync` reads `pyproject.toml` and `uv.lock` and creates a `.venv/` with exactly the pinned dependency versions — you shouldn't need to `pip install` anything by hand. From here on, prefix commands with `uv run` so they execute inside that managed environment.

To run the server directly (mostly useful for a quick sanity check — MCP servers expect a client on the other end of stdio, so running it directly will just sit there waiting):

```bash
uv run server.py
```

## Running the MCP Inspector

The [MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector) is a small web UI for talking to an MCP server directly — no AI model involved — so you can call tools, inspect their schemas, and check responses while you're developing.

Because this project depends on `mcp[cli]`, the easiest way to launch it is through the `mcp` CLI's `dev` command, which starts your server *and* opens the Inspector against it in one step:

```bash
uv run mcp dev server.py
```

This prints a local URL (typically `http://localhost:5173`); open it in a browser. From there you can:

1. See the connected server's declared tools (`add_task`, `list_tasks`) and prompt (`plan_my_day`), with their schemas.
2. Fill in a form for a tool call (e.g. `title`, `category`, `due_date`) and click **Run** to call it against the real server and database.
3. Read the raw JSON-RPC request/response for each call — useful for seeing exactly what the client sent and what the server returned.

If `mcp dev` isn't available in your environment, you can instead run the Inspector standalone and point it at the server's launch command:

```bash
npx @modelcontextprotocol/inspector uv run server.py
```

Either approach talks to the *same* `server.py` — the Inspector is just standing in for the AI client.

## Connecting to Claude Desktop

Claude Desktop launches local MCP servers itself, based on a config file, then talks to them exactly the way described above (stdio transport). To register this server:

1. Open Claude Desktop's MCP server configuration (**Settings → Developer → Edit Config**, or edit `claude_desktop_config.json` directly — this project includes a placeholder file at the repo root for reference).
2. Add an entry that tells Claude Desktop how to start the server, using `uv run` and the **absolute path** to the project:

   ```json
   {
     "mcpServers": {
       "grad-student-task-manager": {
         "command": "uv",
         "args": [
           "--directory",
           "/absolute/path/to/grad-task-mcp",
           "run",
           "server.py"
         ]
       }
     }
   }
   ```

   Replace `/absolute/path/to/grad-task-mcp` with wherever you actually have this project checked out. Using `uv --directory ... run` (rather than relying on your shell's current working directory) is important — Claude Desktop launches the command from its own working directory, not this one.
3. Save the file and fully restart Claude Desktop (quit, don't just close the window).
4. Look for a small tools/plug icon in the chat input, or check **Settings → Developer**, to confirm "Grad Student Task Manager" shows up as a connected server. If it doesn't, check Claude Desktop's MCP logs (**Settings → Developer → Open Logs Folder**) for the startup error — most often it's a wrong path or `uv` not being on `PATH`.
5. Once connected, just talk to Claude normally — e.g. "Add a task: finish problem set 3, due Friday" — and Claude will call `add_task` on your behalf when it judges that's the right action.

## Example tool calls

These are the JSON arguments a client sends when calling each tool (what you'd type into the Inspector's form, or what Claude constructs behind the scenes).

**Add a task with a due date:**

```json
// call: add_task
{
  "title": "Finish MCP assignment",
  "category": "academic",
  "due_date": "2026-09-19"
}
```

```json
// response
{
  "success": true,
  "task_id": 1,
  "message": "Task added successfully."
}
```

**Add a task with no due date:**

```json
// call: add_task
{
  "title": "Call mom",
  "category": "people"
}
```

**List everything:**

```json
// call: list_tasks
{}
```

```json
// response
{
  "success": true,
  "count": 2,
  "tasks": [
    { "id": 1, "title": "Finish MCP assignment", "category": "academic", "due_date": "2026-09-19" },
    { "id": 2, "title": "Call mom", "category": "people", "due_date": null }
  ]
}
```

**List just one category:**

```json
// call: list_tasks
{ "category": "academic" }
```

**Invalid category (rejected before it touches the database):**

```json
// call: add_task
{ "title": "Board the shuttle", "category": "transportation" }
```

```json
// response
{
  "success": false,
  "error": "Category must be one of: academic, life_admin, meeting, other, people, recreational"
}
```

## Input sanitization

Validation lives in `security.py` and runs *before* anything touches the database:

- **`validate_title`**
  - Rejects non-string input.
  - Strips leading/trailing whitespace; rejects an empty (or whitespace-only) result.
  - Enforces a maximum length of 200 characters.
  - Strips ASCII control characters (`\x00`–`\x1f`, `\x7f`) with a regex, so stray characters like null bytes or escape sequences can't sneak into stored titles.
- **`validate_category`**
  - Normalizes case and whitespace, then checks the result against a fixed allow-list (`academic`, `meeting`, `life_admin`, `recreational`, `people`, `other`). Anything else is rejected outright — this is a classic allow-list, not a deny-list, so there's no way to smuggle in an unexpected value.
- **`due_date`** is validated in `server.py` itself, by parsing it with `datetime.strptime(due_date, "%Y-%m-%d")` — if it doesn't match that exact format, the call fails with a clear error instead of storing a malformed date.

**Worth being precise about:** the title sanitizer above cleans up *formatting* (whitespace, length, control characters) — it does **not** strip out characters like `'`, `;`, or `--` that would matter for SQL injection. That's deliberate, not an oversight: this project's actual injection defense lives one layer down, in how the database query is built (see the next section). Conflating "we sanitized the input" with "we're safe from injection" is a common and dangerous mistake, so it's worth being explicit that these are two different mechanisms here.

## SQL injection exploit demonstration

**The attempt.** Suppose a task title is a classic SQL injection payload:

```json
// call: add_task
{
  "title": "'); DROP TABLE tasks; --",
  "category": "academic",
  "due_date": "2026-09-29"
}
```

`validate_title` only strips whitespace/control characters/length — none of which this string has in a way that changes it — so the string is passed through to the database layer essentially unchanged.

**Why it's harmless here.** The insert in `server.py` uses a **parameterized query**:

```python
cursor = connection.execute(
    """
    INSERT INTO tasks (title, category, due_date)
    VALUES (?, ?, ?)
    """,
    (safe_title, safe_category, due_date),
)
```

The `?` placeholders mean the title is handed to SQLite as a *data value* through the driver's binding mechanism, never spliced into the SQL text itself. SQLite has no opportunity to interpret `'`, `;`, or `--` as syntax, because as far as the query parser is concerned, they never appear in the SQL statement at all — they're sitting in a separate parameter slot. This is the actual fix for SQL injection; it's not something `validate_title` is doing.

**Confirming it.** Adding that title, then listing tasks, returns it back as an inert string:

```json
// response to add_task
{ "success": true, "task_id": 2, "message": "Task added successfully." }

// response to list_tasks
{
  "success": true,
  "count": 1,
  "tasks": [
    { "id": 2, "title": "'); DROP TABLE tasks; --", "category": "academic", "due_date": "2026-09-29" }
  ]
}
```

The `tasks` table is untouched — no rows dropped, no schema change, and the string is stored and returned as ordinary text, exactly like any other title. `test_security.py` includes `test_sql_injection_string_is_treated_as_text`, which asserts this same payload survives `validate_title` unchanged (i.e. sanitization isn't expected to catch it), and the parameterized query is what keeps that safe.

**For contrast — what *would* be vulnerable:** if `server.py` instead built the query with string formatting, e.g.

```python
# DO NOT DO THIS — vulnerable, shown only for comparison
connection.execute(
    f"INSERT INTO tasks (title, category, due_date) VALUES ('{safe_title}', '{safe_category}', '{due_date}')"
)
```

then that same payload would close the string literal early and the `DROP TABLE tasks` statement would actually execute. This project doesn't do that anywhere — every query in `database.py`/`server.py` uses `?` placeholders — but it's the difference that matters.

## Rate limiting

`check_rate_limit()` in `security.py` throttles **write** traffic (it's only called from `add_task`, not `list_tasks`):

```python
RATE_LIMIT = 5
RATE_WINDOW_SECONDS = 60
request_times = deque()
```

It's a **sliding-window counter**: every call appends a timestamp to `request_times`, first dropping any timestamps older than 60 seconds. If 5 or more timestamps remain in that trailing 60-second window, the 6th call raises `ValueError("Rate limit exceeded. Please wait before adding more tasks.")` before the task is validated or stored. In effect: at most 5 `add_task` calls per rolling minute.

Note the check happens *first* in `add_task`, before `validate_title`/`validate_category` — so even a call that would otherwise fail validation still consumes one of the 5 slots.

## Rate-limit exploit demonstration

The limiter has two properties worth calling out, because together they make it easy to bypass:

1. **It's in-memory, not persisted.** `request_times` is a plain Python `deque` living in the server process's memory — nothing is written to `tasks.db` or disk.
2. **It's global, not per-client or per-session.** There's a single counter for the entire process; it has no concept of "who" is calling.

**The exploit:** restart the server process, and the limit resets instantly — with zero timestamps in the (brand-new) `request_times`, you immediately have another full budget of 5 calls.

Concretely, with the Inspector or Claude Desktop connected:

```bash
# Terminal 1: call add_task 5 times in under a minute → 5th succeeds, 6th is rejected
# (e.g. via the Inspector's "Run" button, or asking Claude to add 6 tasks quickly)

# response to the 6th call within the same 60s window:
{ "success": false, "error": "Rate limit exceeded. Please wait before adding more tasks." }
```

Then, instead of waiting out the 60-second window:

```bash
# Ctrl+C the running server, then start a fresh process
uv run server.py
# (or: fully restart Claude Desktop, which respawns the server subprocess)
```

The next `add_task` call succeeds immediately — the limiter has no memory of the previous process's 5 calls. Because the MCP host restarts the server subprocess on its own (e.g. any time Claude Desktop itself restarts, or if the process crashes and the host relaunches it), this reset can happen without the caller doing anything deliberate at all. A more robust limiter would persist counts outside the process (e.g. in the SQLite database itself, or in a file/cache keyed by client identity) rather than in an in-memory `deque` scoped to one process's lifetime.

## Why authentication is not required

This server uses MCP's **stdio transport**: Claude Desktop doesn't connect to it over a network — it launches `server.py` as a direct child process and talks to it over that one process's stdin/stdout pipes. There is no listening port, no URL, and no way for any other machine (or any other process on the same machine, for that matter) to open a connection to it the way they could with an HTTP server.

Given that, the trust boundary is the same as running any other local script: whoever can start the process already has exactly the access the process grants — running it *is* the authentication. Adding a username/password or token check on top wouldn't protect anything additional, because the only "client" that can ever talk to this server is the one the local user just launched.

This changes if the transport changes. If this server were instead exposed over MCP's HTTP-based transport — so that it could be reached over a network, potentially by multiple users or from a different machine — then authentication (and almost certainly per-caller rate limiting, see above) would become necessary, because at that point "whoever can reach the port" is a much bigger set of people than "whoever is running Claude Desktop on this laptop."

## Project limitations

- **Rate limiting is easily bypassed.** As shown above, it's an in-memory, per-process, global counter — it resets on restart and doesn't distinguish between callers.
- **No authentication or multi-user support.** Fine for local, single-user, stdio use (see above); not safe to expose over a network as-is.
- **No update, complete, or delete tools.** Tasks can be added and listed, but never marked done or removed — the `completed` column exists in the schema but nothing ever sets it.
- **Single global task list.** There's no per-user separation; anyone/anything talking to the server sees the same `tasks.db`.
- **SQLite, single file, no migrations.** Fine for a class project; would need a real migration story and probably a different database for concurrent multi-user use.
- **Sanitization is intentionally narrow.** `validate_title` only handles whitespace/length/control characters — it isn't, and isn't meant to be, an HTML/markdown escaper. If task titles were ever rendered in a web page, they'd need separate output-encoding, since this layer doesn't do that.
- **`tasks.db` isn't gitignored.** `.gitignore` excludes `.venv`, `__pycache__`, and build artifacts, but not `tasks.db` — the runtime database (including whatever test/demo data ends up in it) can end up committed by accident. Worth adding `tasks.db` to `.gitignore`.
- **Limited automated tests.** `test_security.py` covers `validate_title`, `validate_category`, and `check_rate_limit` well, but there's no test coverage for `database.py` or the tool functions in `server.py` themselves (e.g. no integration test that actually calls `add_task`/`list_tasks` end to end).
- **`due_date` isn't range- or sanity-checked.** `"2020-01-01"` or `"2099-12-31"` are both accepted as long as they parse — there's no check that a due date is reasonable or in the future.
- **The packaged `grad-task-mcp` CLI entry point is a stub.** `pyproject.toml` defines a console script (`grad-task-mcp = "grad_task_mcp:main"`) pointing at `src/grad_task_mcp/__init__.py`, but that `main()` just prints a placeholder greeting — it's unrelated to the actual server in `server.py`. Use `uv run server.py` (or `uv run mcp dev server.py`) to run the real thing, not the `grad-task-mcp` command.

## Repository structure

```
grad-task-mcp/
├── server.py                  # MCP server: defines the mcp instance, add_task and
│                               # list_tasks tools, and the plan_my_day prompt
├── security.py                # Input validation (validate_title, validate_category)
│                               # and the rate limiter (check_rate_limit)
├── database.py                # SQLite connection helper + schema creation
├── test_security.py           # pytest tests for security.py
├── tasks.db                   # SQLite database file (created automatically on first run)
├── pyproject.toml             # Project metadata, dependencies, uv/build config
├── uv.lock                    # Locked dependency versions (generated by uv)
├── requirements.txt           # Exported pinned dependencies (via `uv pip compile`)
├── .python-version            # Pins the Python version (3.12) for uv
├── .gitignore                 # Excludes .venv, __pycache__, build artifacts
├── claude_desktop_config.json # Example/placeholder Claude Desktop MCP config
├── README.md                  # This file
└── src/
    └── grad_task_mcp/
        └── __init__.py        # Packaged CLI stub (see Limitations — not the server)
```
