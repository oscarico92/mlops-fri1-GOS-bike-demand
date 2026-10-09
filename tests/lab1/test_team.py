import pytest

from bike_demand.team import normalize_team_slug

pytestmark = pytest.mark.lab1


def test_trims_and_lowercases():
    assert normalize_team_slug("  Team Blue  ") == "team-blue"


def test_joins_whitespace_with_hyphens():
    assert normalize_team_slug("Team   Blue\tNorth") == "team-blue-north"


def test_rejects_blank_names():
    with pytest.raises(ValueError, match="non-whitespace"):
        normalize_team_slug("   ")


def test_mixed_whitespace_and_case_collapse_to_one_slug():
    assert normalize_team_slug("\n SPARROWS \t\n  North ") == "sparrows-north"
    assert normalize_team_slug("Sparrows") == "sparrows"
    with pytest.raises(ValueError, match="non-whitespace"):
        normalize_team_slug("\t\n")
