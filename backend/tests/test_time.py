from app.utils.time import format_duration


def test_duration_under_hour() -> None:
    assert format_duration(61) == "1:01"


def test_duration_over_hour() -> None:
    assert format_duration(3661) == "1:01:01"
