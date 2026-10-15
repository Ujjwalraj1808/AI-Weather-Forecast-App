"""City disambiguation, run against hand-written search fixtures (no network)."""

import pytest

from src.weather import client as weather_client
from tests.conftest import LOCATIONS, fake_search


@pytest.fixture(autouse=True)
def offline_search(monkeypatch):
    monkeypatch.setattr(weather_client, "search_locations", fake_search)
    monkeypatch.delenv("PREFERRED_COUNTRY", raising=False)


def resolve(text):
    loc = weather_client.resolve_location(text)
    return loc["name"], loc["country"]


def test_delhi_resolves_to_india_not_canada():
    """Regression: live search for "Delhi" lists only Delhi, Ontario, Canada."""
    loc = weather_client.resolve_location("Delhi")
    assert (loc["id"], loc["country"]) == (1112321, "India")


def test_preferred_country_search_only_when_needed(monkeypatch):
    seen = []
    monkeypatch.setattr(weather_client, "search_locations", lambda q: seen.append(q) or fake_search(q))
    weather_client.resolve_location("Muzaffarpur")
    assert seen == ["Muzaffarpur"]
    seen.clear()
    weather_client.resolve_location("Delhi")
    assert seen == ["Delhi", "Delhi, India"]


def test_delhi_india_explicit():
    assert resolve("Delhi, India") == ("Delhi", "India")


def test_delhi_canada_still_reachable():
    assert resolve("Delhi, Canada") == ("Delhi", "Canada")


def test_muzaffarpur_india():
    assert resolve("Muzaffarpur, India") == ("Muzaffarpur", "India")
    assert resolve("Muzaffarpur") == ("Muzaffarpur", "India")


def test_london_uk_alias():
    assert resolve("London, UK") == ("London", "United Kingdom")


def test_paris_france():
    assert resolve("Paris, France") == ("Paris", "France")


def test_bare_international_name_without_preferred_match_asks_user():
    with pytest.raises(weather_client.AmbiguousLocationError) as exc:
        weather_client.resolve_location("London")
    assert {c["country"] for c in exc.value.candidates} == {"United Kingdom", "Canada"}


def test_ambiguous_name_returns_all_exact_matches():
    with pytest.raises(weather_client.AmbiguousLocationError) as exc:
        weather_client.resolve_location("Springfield")
    assert [c["region"] for c in exc.value.candidates] == ["Massachusetts", "Missouri", "Ohio", "Virginia"]


def test_region_qualifier_breaks_ambiguity():
    assert weather_client.resolve_location("Springfield, Missouri")["id"] == 2606548


def test_paris_bare_name_single_match():
    assert resolve("Paris") == ("Paris", "France")


def test_preferred_country_is_configurable(monkeypatch):
    monkeypatch.setenv("PREFERRED_COUNTRY", "Canada")
    assert resolve("Delhi") == ("Delhi", "Canada")


def test_qualifier_with_no_match_is_not_found():
    with pytest.raises(weather_client.CityNotFoundError):
        weather_client.resolve_location("Paris, India")


def test_unknown_city_is_not_found():
    with pytest.raises(weather_client.CityNotFoundError):
        weather_client.resolve_location("Atlantis")


def test_gurugram_is_searched_as_gurgaon(monkeypatch):
    seen = []
    monkeypatch.setattr(
        weather_client,
        "search_locations",
        lambda q: seen.append(q) or [dict(LOCATIONS["muzaffarpur"][0], name="Gurgaon", id=99)],
    )
    assert weather_client.resolve_location("Gurugram")["id"] == 99
    assert seen == ["gurgaon"]


@pytest.mark.parametrize("query", ["id:2801268", "28.61,77.21", "-33.9, 18.4", "iata:DEL", "auto:ip"])
def test_exact_queries_skip_search(query, monkeypatch):
    monkeypatch.setattr(weather_client, "search_locations", None)
    assert weather_client.resolve_query(query) == query
