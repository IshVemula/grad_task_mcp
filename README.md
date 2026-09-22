# Grad Student Task Manager MCP

- Ishitha Reddy Vemula
  
## Overview

The **Grad Student Task Manager** is a Python-based Model Context Protocol (MCP) server built in the **Personal Productivity** domain.

The server allows an MCP client such as Claude Desktop to manage a graduate student's tasks through natural-language requests.

The project demonstrates:

- MCP tools
- MCP prompts
- Prompt Template
- Local SQLite storage
- Input validation
- SQL injection protection
- Rate limiting
- Safe error handling
- Secret/configuration management using `.env`
- File path management using `pathlib.Path`
- Integration with Claude Desktop
- Testing through MCP Inspector

---

## Domain

**Personal Productivity**

The server focuses on graduate student task management.

It allows users to:

- Add tasks
- View tasks
- Update tasks
- Mark tasks as completed
- Delete tasks
- Use a reusable prompt to organize tasks into a daily plan

---

## Architecture

The system follows this general flow:

```text
User
  |
  v
Claude Desktop
  |
  | MCP over stdio
  v
Python MCP Server
  |
  |-- server.py
  |-- security.py
  |-- database.py
  |-- config.py
  |
  v
SQLite Database
```

### Components

#### User

The user interacts with Claude Desktop using natural language.

Example:

```text
Add an academic task called "Finish MCP documentation" due September 24, 2026.
```

#### Claude Desktop

Claude Desktop acts as the **MCP client**.

It:

- Receives the user's natural-language request
- Determines which MCP tool should be used
- Calls the MCP server
- Receives the MCP response
- Presents the result back to the user

#### `server.py`

This is the main MCP server file.

It:

- Creates the MCP server
- Registers MCP tools
- Registers the MCP prompt
- Handles requests and responses
- Connects security and database functionality

The server currently exposes four tools:

- `add_task()`
- `list_tasks()`
- `update_task()`
- `delete_task()`

It also exposes one prompt:

- `plan_my_day()`

#### `security.py`

This file contains security-related logic.

It is responsible for:

- Input validation
- Task title sanitization
- Category validation
- Rate limiting

#### `database.py`

This file handles database access.

It:

- Creates the SQLite database
- Creates the `tasks` table
- Opens database connections
- Uses parameterized SQL queries
- Reads and writes task data

#### `config.py`

This file handles local configuration.

It:

- Loads values from `.env`
- Uses `python-dotenv`
- Uses `pathlib.Path`
- Avoids using `os.path`

#### `tasks.db`

This is the local SQLite database.

It stores:

- Task ID
- Task title
- Category
- Due date
- Completion status

The database file is excluded from Git.

---

## MCP Tools

## 1. Add Task

### Tool

```text
add_task()
```

### Purpose

Creates a new task.

### Inputs

- `title`
- `category`
- optional `due_date`

### Supported Categories

- `academic`
- `meeting`
- `life_admin`
- `recreational`
- `people`
- `other`

The category is defined using a fixed list of values so MCP clients can display it as a dropdown where supported.

The due date is defined as a Python `date` type so MCP clients can treat it as a date input where supported.

### Example

```text
Add an academic task called "Finish Decision Analysis assignment" due September 25, 2026.
```

---

## 2. List Tasks

### Tool

```text
list_tasks()
```

### Purpose

Returns incomplete tasks.

The user can optionally filter tasks by category.

### Example

```text
Show me all of my academic tasks.
```

The tool is treated as read-only because it does not modify stored data.

---

## 3. Update Task

### Tool

```text
update_task()
```

### Purpose

Updates an existing task using its unique task ID.

The tool can update:

- title
- category
- due date
- completion status

### Example

```text
Mark task 4 as completed.
```

or:

```text
Change task 4's title to "Finish final MCP documentation".
```

A separate `complete_task()` tool was not created because completion is simply one type of update.

This keeps the MCP interface smaller and avoids unnecessary duplicate functionality.

---

## 4. Delete Task

### Tool

```text
delete_task()
```

### Purpose

Deletes a task using its unique task ID.

### Example

```text
Delete task 7.
```

This tool is considered destructive because it permanently removes data.

---

## MCP Prompt

## Plan My Day

### Prompt

```text
plan_my_day()
```

### Purpose

Provides reusable instructions to help Claude organize a graduate student's tasks into a realistic daily plan.

### Priority Options

- `balanced`
- `deadlines`
- `academic`
- `personal`

### Example

```text
Use my current tasks and create a balanced plan for my day.
```
### Prompt Template

The `plan_my_day` prompt uses the following reusable template:

```text
You are helping a graduate student organize their day based on their current task list.

Planning priority: {priority}

Review the available tasks and create a realistic daily plan.

Guidelines:
- Prioritize tasks with the nearest deadlines.
- Identify the three most important tasks.
- Group similar tasks when possible.
- Separate academic work, meetings, and personal tasks.
- Include reasonable breaks.
- Avoid scheduling every minute of the day.
- If everything cannot realistically be completed, suggest which tasks should be moved to another day.

Return the plan in a clear, easy-to-follow format.
```

The prompt focuses on:

- Upcoming deadlines
- Realistic scheduling
- Grouping similar work
- Reasonable breaks
- Separating academic, meeting, and personal responsibilities
- Identifying the three most important tasks
- Moving lower-priority work to another day when necessary

---

## Project Structure

```text
grad-task-mcp/
|
|-- server.py
|-- database.py
|-- security.py
|-- config.py
|-- test_security.py
|
|-- .env.example
|-- .gitignore
|
|-- README.md
|-- requirements.txt
|-- claude_desktop_config.json
|-- pyproject.toml
|-- uv.lock
```

The following files may exist locally but are intentionally excluded from Git:

```text
.env
tasks.db
.venv/
__pycache__/
```

---

## Requirements

The project requires:

- Python 3.10 or newer
- `uv`
- Claude Desktop
- Node.js / `npx` for MCP Inspector

---

## Installation

### 1. Clone the Repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd grad-task-mcp
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with the actual GitHub repository URL.

### 2. Install Dependencies

Using `uv`:

```bash
uv sync
```

If required, install Python through `uv`:

```bash
uv python install 3.12
```

The project can then be run using the Python environment managed by `uv`.

### 3. Create the Local Environment File

The repository includes:

```text
.env.example
```

Create a local `.env` file based on it.

Example:

```text
APP_NAME=Grad Student Task Manager
```

The local `.env` file must not be committed to Git.

---

## Secret Management

The current server does not require external API credentials because it runs locally and uses a local SQLite database.

However, the project is structured to safely support secrets or credentials in the future.

Local values are stored in:

```text
.env
```

The `.env` file is excluded from version control using `.gitignore`.

A safe example file is included in the repository:

```text
.env.example
```

Example:

```text
APP_NAME=Grad Student Task Manager

# Example future secret:
# SOME_API_KEY=replace_with_your_key
```

File paths are constructed using:

```python
from pathlib import Path
```

instead of:

```python
os.path
```

This follows the project's secret-management and file-path requirements.

---

## Database

The project uses SQLite.

The database is created automatically when the server starts.

The main table is:

```text
tasks
```

It contains:

```text
id
title
category
due_date
completed
```

The database is stored locally as:

```text
tasks.db
```

The database file is excluded from Git.

---

## Running the MCP Server

Run:

```bash
uv run python server.py
```

The server communicates using MCP over standard input/output (`stdio`).

Because it is a `stdio` server, it may appear to do nothing when run directly.

This is expected.

The server is waiting for an MCP client to communicate with it.

Use:

```text
Control + C
```

to stop the server.

---

## Testing with MCP Inspector

Run:

```bash
uv run mcp dev server.py
```

MCP Inspector can be used to verify that the server exposes:

### Tools

- Add Task
- List Tasks
- Update Task
- Delete Task

### Prompt

- Plan My Day

The Inspector is also useful for testing exact inputs and security exploit scenarios.

---

## Claude Desktop Integration

The server can be accessed through Claude Desktop.

Claude Desktop acts as the MCP client and can automatically choose the appropriate tool based on natural-language requests.

Examples:

### Add Task

```text
Add an academic task called "Finish MCP documentation" due September 24, 2026.
```

### List Tasks

```text
Show me all of my academic tasks.
```

### Update Task

```text
Mark task 3 as completed.
```

### Rename Task

```text
Change task 3's title to "Finish final MCP documentation".
```

### Delete Task

```text
Delete task 5.
```

---

## Claude Desktop Configuration

The repository includes an example configuration file:

```text
claude_desktop_config.json
```

Example:

```json
{
  "mcpServers": {
    "Grad Student Task Manager": {
      "command": "/ABSOLUTE/PATH/TO/uv",
      "args": [
        "run",
        "--with",
        "mcp[cli]",
        "mcp",
        "run",
        "/ABSOLUTE/PATH/TO/grad-task-mcp/server.py"
      ]
    }
  }
}
```

The placeholder paths must be replaced with the absolute paths on the user's machine.

The actual Claude Desktop configuration file is stored separately from the GitHub repository.

---

# Security Best Practices

The project implements two primary best practices:

1. Input sanitization and SQL injection protection
2. Rate limiting

---

## Best Practice 1: Input Sanitization and SQL Injection Protection

User-provided task titles and categories are validated before database operations.

Task titles:

- cannot be empty
- cannot exceed the maximum length
- have control characters removed

Categories must match one of the supported categories.

The database also uses **parameterized SQL queries**.

Example:

```python
connection.execute(
    """
    INSERT INTO tasks (
        title,
        category,
        due_date
    )
    VALUES (?, ?, ?)
    """,
    (
        safe_title,
        safe_category,
        due_date_value,
    ),
)
```

User-provided values are passed separately from the SQL query.

This prevents user input from being interpreted as executable SQL.

---

## SQL Injection Exploit Test

A malicious task title can be submitted:

```text
'); DROP TABLE tasks; --
```

A vulnerable application might interpret this as SQL and attempt to delete the `tasks` table.

In this server, the text is treated only as task data.

After submitting the malicious string:

```text
'); DROP TABLE tasks; --
```

the `list_tasks()` tool continues to work and the database remains intact.

This demonstrates that parameterized SQL prevents the injection attack.

---

## Best Practice 2: Rate Limiting

The server limits state-changing operations to:

```text
5 operations per 60 seconds
```

Rate limiting applies to:

- `add_task()`
- `update_task()`
- `delete_task()`

The read-only `list_tasks()` operation is not rate limited.

This is intentional because reading information does not modify application state.

---

## Rate-Limit Exploit Test

A user or AI agent can attempt more than five write operations within 60 seconds.

For example:

```text
Request 1 -> accepted
Request 2 -> accepted
Request 3 -> accepted
Request 4 -> accepted
Request 5 -> accepted
Request 6 -> blocked
```

The sixth request returns an error similar to:

```text
Rate limit exceeded. Please wait before modifying more tasks.
```

This reduces the risk of:

- accidental loops
- excessive repeated writes
- runaway agent behavior
- basic request abuse

---

## Error Handling

The server avoids exposing unnecessary internal error information.

For example, database exceptions are not returned directly to the user.

Instead of exposing internal SQLite details, the server returns messages such as:

```text
The task could not be saved because of a database error.
```

This improves usability and avoids disclosing unnecessary implementation details.

---

## Authentication

No external authentication is currently required.

The server:

- runs locally
- communicates through `stdio`
- stores information locally in SQLite
- does not access third-party APIs
- does not expose a public HTTP endpoint

If a future version connects to external services such as Google Calendar or Gmail, authentication credentials would be stored securely using the `.env` configuration approach.

---

## Automated Tests

Security tests are included in:

```text
test_security.py
```

Run the tests using:

```bash
uv run pytest
```

The automated tests cover:

- Valid task titles
- Invalid categories
- Excessively long task titles
- SQL injection strings being treated as text
- Rate-limit enforcement

A successful test run should produce output similar to:

```text
5 passed
```

---

## Manual MCP Testing

The tools should also be tested manually in MCP Inspector.

Recommended test sequence:

### 1. Add Task

Create a task:

```text
Title:
MCP Inspector Test Task

Category:
academic

Due Date:
2026-09-25
```

### 2. List Tasks

Run:

```text
list_tasks
```

Confirm that the new task appears.

### 3. Update Task

Update the task title or completion status.

Example:

```text
Task ID:
1

Title:
Updated MCP Inspector Task
```

Then run `list_tasks()` again to confirm the change.

### 4. Complete Task

Set:

```text
completed = true
```

The task should no longer appear in the active task list.

### 5. Delete Task

Create a temporary task and delete it using its ID.

Then run `list_tasks()` again and confirm that it has been removed.

### 6. Test the Prompt

Open the MCP Inspector prompt section.

Run:

```text
plan_my_day
```

with a priority such as:

```text
balanced
```

Confirm that the server returns the reusable planning instructions.

---

## Claude Desktop Testing

Each tool should also be tested through Claude Desktop.

Recommended examples:

### Add

```text
Add an academic task called "Claude Test Task" due September 26, 2026.
```

### List

```text
Show me all my academic tasks.
```

### Update

```text
Change "Claude Test Task" to "Updated Claude Test Task".
```

### Complete

```text
Mark "Updated Claude Test Task" as completed.
```

### Delete

```text
Add a task called "Delete Me Claude" in the other category.
```

Then:

```text
Delete "Delete Me Claude".
```

This confirms that Claude Desktop can discover and use the MCP server successfully.

---

## Design Decisions

### Why Separate Add, List, Update, and Delete?

Each tool represents a distinct user action.

- `add_task()` creates data
- `list_tasks()` reads data
- `update_task()` changes data
- `delete_task()` removes data

These operations are intentionally separate because they have different behaviors and different safety implications.

### Why Not Create Separate Update Tools?

The server does not use separate tools such as:

```text
rename_task()
complete_task()
change_due_date()
```

Instead, these actions are handled through:

```text
update_task()
```

This avoids creating too many similar tools.

It also makes the interface easier for an LLM to understand and reduces unnecessary duplication.

---

## Limitations

The current implementation is intended for a single local user.

Current limitations include:

- Tasks are stored only on one machine
- There is no synchronization across devices
- SQLite is intended for local use rather than large multi-user applications
- The rate limiter is stored in application memory
- Restarting the server resets the rate limiter
- There is no user account system
- There are no recurring tasks
- There are no reminder notifications
- There is no calendar synchronization
- The visual appearance of MCP input fields depends on the MCP client
- A typed date field may not display as a calendar picker in every MCP client

---

## Future Improvements

Future versions could include:

- Google Calendar integration
- Reminder notifications
- Task priorities
- Recurring tasks
- Persistent rate limiting using Redis
- User authentication
- Cloud synchronization
- Better filtering and sorting
- Task search
- Task history
- Multiple users
- Hosted MCP transport

---

## Code References

MCP server initialization and tool/prompt patterns were adapted from the official MCP Python SDK documentation.

MCP Documentation:

https://modelcontextprotocol.io/

MCP Python SDK:

https://github.com/modelcontextprotocol/python-sdk

MCP Example Servers:

https://github.com/modelcontextprotocol/servers

Where code is directly adapted from an external source, the corresponding source is referenced in a code comment.

---

## Technologies Used

- Python
- Model Context Protocol
- MCP Python SDK
- SQLite
- Pydantic
- python-dotenv
- pathlib
- pytest
- uv
- Claude Desktop
- MCP Inspector

---

## Summary

The Grad Student Task Manager demonstrates how an MCP server can expose structured tools and prompts to an AI client while maintaining basic software engineering and security practices.

The project includes:

- Four MCP tools
- One MCP prompt
- SQLite persistence
- Input validation
- Parameterized SQL
- SQL injection protection
- Rate limiting
- Error handling
- Safe local configuration
- Automated testing
- MCP Inspector testing
- Claude Desktop integration

The result is a small but complete example of using MCP to connect an AI assistant to a local productivity application.
