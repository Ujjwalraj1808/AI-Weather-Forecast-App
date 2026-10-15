import pytest

from src.weather.scenes import SCENES, is_golden_hour, scene_for

NOON = "2026-10-15 12:00"
MIDNIGHT = "2026-10-15 00:30"
SUNRISE, SUNSET = "06:15 AM", "05:50 PM"


@pytest.mark.parametrize(
    ("code", "is_day", "localtime", "expected"),
    [
        (1000, True, NOON, "clear-day"),
        (1000, False, MIDNIGHT, "clear-night"),
        (1003, True, NOON, "clear-day"),
        (1000, True, "2026-10-15 06:30", "golden"),
        (1000, True, "2026-10-15 17:30", "golden"),
        (1006, True, NOON, "cloudy-day"),
        (1009, False, MIDNIGHT, "cloudy-night"),
        (1063, True, NOON, "rain"),
        (1153, True, NOON, "rain"),
        (1195, False, MIDNIGHT, "rain"),
        (1243, True, NOON, "rain"),
        (1087, True, NOON, "storm"),
        (1276, False, MIDNIGHT, "storm"),
        (1282, True, NOON, "storm"),
        (1066, True, NOON, "snow"),
        (1117, True, NOON, "snow"),
        (1225, True, NOON, "snow"),
        (1204, True, NOON, "snow"),
        (1030, True, NOON, "fog"),
        (1135, False, MIDNIGHT, "fog"),
        (1147, True, NOON, "fog"),
        (4242, True, NOON, "default"),
    ],
)
def test_scene_for(code, is_day, localtime, expected):
    assert scene_for(code, is_day, localtime, SUNRISE, SUNSET) == expected


def test_golden_hour_only_applies_to_clear_skies():
    assert scene_for(1183, True, "2026-10-15 06:30", SUNRISE, SUNSET) == "rain"


def test_golden_hour_handles_polar_day():
    assert is_golden_hour(NOON, "No sunrise", "No sunset") is False


def test_every_scene_has_css():
    from pathlib import Path

    css = (Path(__file__).resolve().parent.parent / "static" / "style.css").read_text()
    for scene in SCENES:
        assert f'[data-scene="{scene}"]' in css, scene
