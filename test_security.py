import pytest

from security import (
    validate_title,
    validate_category,
    check_rate_limit,
    request_times,
)


def test_valid_title():
    result = validate_title("Finish MCP assignment")
    assert result == "Finish MCP assignment"


def test_invalid_category():
    with pytest.raises(ValueError):
        validate_category("banana")


def test_long_title():
    long_title = "a" * 201

    with pytest.raises(ValueError):
        validate_title(long_title)


def test_sql_injection_string_is_treated_as_text():
    malicious_input = "'); DROP TABLE tasks; --"

    result = validate_title(malicious_input)

    assert result == malicious_input


def test_rate_limit_blocks_sixth_request():
    request_times.clear()

    for _ in range(5):
        check_rate_limit()

    with pytest.raises(ValueError):
        check_rate_limit()