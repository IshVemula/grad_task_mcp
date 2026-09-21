import sqlite3

from datetime import date
from typing import Annotated, Literal

from pydantic import Field

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from config import APP_NAME
from database import get_connection, initialize_database
from security import (
    check_rate_limit,
    validate_category,
    validate_title,
)


# MCP server initialization follows the official MCP Python SDK pattern:
# https://github.com/modelcontextprotocol/python-sdk
mcp = MCPServer(APP_NAME)

initialize_database()


TaskCategory = Literal[
    "academic",
    "meeting",
    "life_admin",
    "recreational",
    "people",
    "other",
]


TaskID = Annotated[
    int,
    Field(
        gt=0,
        description="Unique numeric ID of the task.",
    ),
]


TaskTitle = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        description="Short description of the task.",
    ),
]


DueDate = Annotated[
    date,
    Field(
        description="Due date for the task.",
    ),
]


@mcp.tool(
    title="Add Task",
    description="Create a new task in the graduate student's task list.",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    ),
)
def add_task(
    title: TaskTitle,
    category: Annotated[
        TaskCategory,
        Field(
            description="Category used to organize the task.",
        ),
    ],
    due_date: DueDate | None = None,
) -> dict:
    """
    Add a new task.

    Category must be one of the supported task categories.
    Due date is optional.
    """

    try:
        check_rate_limit()

        safe_title = validate_title(title)
        safe_category = validate_category(category)

        due_date_value = (
            due_date.isoformat()
            if due_date is not None
            else None
        )

        connection = get_connection()

        cursor = connection.execute(
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
            "error": (
                "The task could not be saved because "
                "of a database error."
            ),
        }


@mcp.tool(
    title="List Tasks",
    description="View incomplete tasks, optionally filtered by category.",
    annotations=ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
def list_tasks(
    category: Annotated[
        TaskCategory | None,
        Field(
            description=(
                "Optional category used to filter tasks."
            ),
        ),
    ] = None,
) -> dict:
    """
    List incomplete tasks.

    If a category is provided, only tasks from that category are returned.
    """

    try:
        connection = get_connection()

        if category is not None:
            safe_category = validate_category(category)

            cursor = connection.execute(
                """
                SELECT
                    id,
                    title,
                    category,
                    due_date,
                    completed
                FROM tasks
                WHERE completed = 0
                AND category = ?
                ORDER BY
                    due_date IS NULL,
                    due_date
                """,
                (safe_category,),
            )

        else:
            cursor = connection.execute(
                """
                SELECT
                    id,
                    title,
                    category,
                    due_date,
                    completed
                FROM tasks
                WHERE completed = 0
                ORDER BY
                    due_date IS NULL,
                    due_date
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
                "completed": bool(row[4]),
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
            "error": (
                "Tasks could not be retrieved because "
                "of a database error."
            ),
        }


@mcp.tool(
    title="Update Task",
    description=(
        "Update the title, category, due date, "
        "or completion status of an existing task."
    ),
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
def update_task(
    task_id: TaskID,
    title: TaskTitle | None = None,
    category: Annotated[
        TaskCategory | None,
        Field(
            description="New category for the task.",
        ),
    ] = None,
    due_date: DueDate | None = None,
    completed: Annotated[
        bool | None,
        Field(
            description=(
                "Set to true to mark the task complete "
                "or false to keep it active."
            ),
        ),
    ] = None,
) -> dict:
    """
    Update one or more fields of an existing task.
    """

    try:
        check_rate_limit()

        updates = []
        values = []

        if title is not None:
            safe_title = validate_title(title)

            updates.append("title = ?")
            values.append(safe_title)

        if category is not None:
            safe_category = validate_category(category)

            updates.append("category = ?")
            values.append(safe_category)

        if due_date is not None:
            updates.append("due_date = ?")
            values.append(due_date.isoformat())

        if completed is not None:
            updates.append("completed = ?")
            values.append(
                1 if completed else 0
            )

        if not updates:
            return {
                "success": False,
                "error": (
                    "No fields were provided to update."
                ),
            }

        values.append(task_id)

        connection = get_connection()

        cursor = connection.execute(
            f"""
            UPDATE tasks
            SET {", ".join(updates)}
            WHERE id = ?
            """,
            values,
        )

        connection.commit()

        if cursor.rowcount == 0:
            connection.close()

            return {
                "success": False,
                "error": (
                    f"No task found with ID {task_id}."
                ),
            }

        connection.close()

        return {
            "success": True,
            "message": (
                f"Task {task_id} updated successfully."
            ),
        }

    except ValueError as error:
        return {
            "success": False,
            "error": str(error),
        }

    except sqlite3.Error:
        return {
            "success": False,
            "error": (
                "The task could not be updated because "
                "of a database error."
            ),
        }


@mcp.tool(
    title="Delete Task",
    description="Delete an existing task using its task ID.",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
def delete_task(
    task_id: TaskID,
) -> dict:
    """
    Permanently delete a task.
    """

    try:
        check_rate_limit()

        connection = get_connection()

        cursor = connection.execute(
            """
            DELETE FROM tasks
            WHERE id = ?
            """,
            (task_id,),
        )

        connection.commit()

        if cursor.rowcount == 0:
            connection.close()

            return {
                "success": False,
                "error": (
                    f"No task found with ID {task_id}."
                ),
            }

        connection.close()

        return {
            "success": True,
            "message": (
                f"Task {task_id} deleted successfully."
            ),
        }

    except ValueError as error:
        return {
            "success": False,
            "error": str(error),
        }

    except sqlite3.Error:
        return {
            "success": False,
            "error": (
                "The task could not be deleted because "
                "of a database error."
            ),
        }


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
# https://github.com/modelcontextprotocol/python-sdk
if __name__ == "__main__":
    mcp.run()