import re
import time
from collections import deque


ALLOWED_CATEGORIES = {
    "academic",
    "meeting",
    "life_admin",
    "recreational",
    "people",
    "other",
}

MAX_TITLE_LENGTH = 200

RATE_LIMIT = 5
RATE_WINDOW_SECONDS = 60

request_times = deque()


def validate_title(title: str) -> str:
    """
    Validate and clean a task title.
    """

    if not isinstance(title, str):
        raise ValueError("Task title must be text.")

    title = title.strip()

    if not title:
        raise ValueError("Task title cannot be empty.")

    if len(title) > MAX_TITLE_LENGTH:
        raise ValueError(
            f"Task title cannot exceed {MAX_TITLE_LENGTH} characters."
        )

    # Remove control characters.
    title = re.sub(r"[\x00-\x1f\x7f]", "", title)

    return title


def validate_category(category: str) -> str:
    """
    Validate a task category.
    """

    category = category.strip().lower()

    if category not in ALLOWED_CATEGORIES:
        raise ValueError(
            "Category must be one of: "
            + ", ".join(sorted(ALLOWED_CATEGORIES))
        )

    return category


def check_rate_limit(limit: int = RATE_LIMIT):
    """
    Allow at most `limit` state-changing operations every 60 seconds (five by default).
    """

    now = time.time()

    while request_times and now - request_times[0] > RATE_WINDOW_SECONDS:
        request_times.popleft()

    if len(request_times) >= limit:
        raise ValueError(
            "Rate limit exceeded. Please wait before modifying more tasks."
        )

    request_times.append(now)