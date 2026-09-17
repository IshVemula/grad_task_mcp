import sqlite3
from datetime import datetime

from mcp.server import MCPServer

from database import get_connection, initialize_database
from security import (
    check_rate_limit,
    validate_category,
    validate_title,
)

# MCP server initialization follows the official MCP Python SDK pattern:
# https://py.sdk.modelcontextprotocol.io/
mcp = MCPServer("Grad Student Task Manager")

initialize_database()


# @mcp.tool() decorator usage matches the official MCP Python SDK pattern:
# https://py.sdk.modelcontextprotocol.io/
# (drafted with ChatGPT, which reproduced this documented pattern)
@mcp.tool()
def add_task(
    title: str,
    category: str,
    due_date: str | None = None,
) -> dict:
    """
    Add a new task to the graduate student's task list.

    Categories:
    academic, meeting, life_admin, recreational, people, other.

    due_date should use YYYY-MM-DD format when provided.
    """

    try:
        check_rate_limit()

        safe_title = validate_title(title)
        safe_category = validate_category(category)

        if due_date:
            try:
                datetime.strptime(due_date, "%Y-%m-%d")
            except ValueError:
                return {
                    "success": False,
                    "error": "Due date must use YYYY-MM-DD format.",
                }

        connection = get_connection()

        cursor = connection.execute(
            """
            INSERT INTO tasks (title, category, due_date)
            VALUES (?, ?, ?)
            """,
            (safe_title, safe_category, due_date),
        )

        connection.commit()

        task_id = cursor.lastrowid

        connection.close()

        return {
            "success": True,
            "task_id": task_id,
            "message": "Task added successfully.",
        }

    except ValueError as error:
        return {
            "success": False,
            "error": str(error),
        }

    except sqlite3.Error:
        return {
            "success": False,
            "error": "The task could not be saved because of a database error.",
        }


# @mcp.tool() decorator usage matches the official MCP Python SDK pattern:
# https://py.sdk.modelcontextprotocol.io/
# (drafted with ChatGPT, which reproduced this documented pattern)
@mcp.tool()
def list_tasks(category: str | None = None) -> dict:
    """
    List incomplete tasks.

    Optionally filter tasks by category.
    """

    try:
        connection = get_connection()

        if category:
            safe_category = validate_category(category)

            cursor = connection.execute(
                """
                SELECT id, title, category, due_date
                FROM tasks
                WHERE completed = 0 AND category = ?
                ORDER BY due_date IS NULL, due_date
                """,
                (safe_category,),
            )

        else:
            cursor = connection.execute(
                """
                SELECT id, title, category, due_date
                FROM tasks
                WHERE completed = 0
                ORDER BY due_date IS NULL, due_date
                """
            )

        rows = cursor.fetchall()

        connection.close()

        tasks = [
            {
                "id": row[0],
                "title": row[1],
                "category": row[2],
                "due_date": row[3],
            }
            for row in rows
        ]

        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks,
        }

    except ValueError as error:
        return {
            "success": False,
            "error": str(error),
        }

    except sqlite3.Error:
        return {
            "success": False,
            "error": "Tasks could not be retrieved because of a database error.",
        }


# @mcp.prompt() decorator usage matches the official MCP Python SDK docs:
# https://py.sdk.modelcontextprotocol.io/servers/prompts/
# (drafted with ChatGPT, which reproduced this documented pattern)
@mcp.prompt()
def plan_my_day(priority: str = "balanced") -> str:
    """
    Create instructions for organizing a graduate student's daily tasks.
    """

    return f"""
You are helping a graduate student plan their day.

Use their available tasks to create a realistic daily plan.

Planning priority: {priority}

Follow these rules:
1. Prioritize tasks with upcoming deadlines.
2. Group similar tasks where practical.
3. Do not schedule every minute of the day.
4. Include reasonable breaks.
5. Separate academic work, meetings, and personal responsibilities.
6. Clearly identify the three most important tasks.
7. If there are too many tasks for one day, recommend what should move to another day.
"""


# stdio server launch pattern adapted from the official MCP Python SDK:
# https://py.sdk.modelcontextprotocol.io/get-started/real-host/
if __name__ == "__main__":
    mcp.run()