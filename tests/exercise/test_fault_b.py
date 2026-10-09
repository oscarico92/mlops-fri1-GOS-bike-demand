"""Fault B (team design): a well-formed date that does not exist in the calendar.

2011 is not a leap year, so `2011-02-29` matches the YYYY-MM-DD format but is not a
real day. A format-only check would accept it; the contract requires parseable dates.
Leap days in 2012 are real and appear in the canonical CSV, so they must stay valid.
"""

from pathlib import Path

import pandas as pd
import pytest

from bike_demand.validate import load_data

pytestmark = pytest.mark.exercise
FIXTURES = Path(__file__).parents[1] / "fixtures"
FAULT_B = FIXTURES / "feb-29-non-leap-year.csv"


def test_fault_b_rejects_feb_29_in_non_leap_year():
    before = FAULT_B.read_bytes()
    with pytest.raises(ValueError, match="dteday: invalid date values"):
        load_data(FAULT_B)
    assert FAULT_B.read_bytes() == before


@pytest.mark.parametrize("valid_day", ["2011-02-28", "2012-02-29"])
def test_fault_b_controls_real_days_are_accepted(tmp_path, valid_day):
    frame = pd.read_csv(FAULT_B, dtype=str)
    frame.loc[frame["instant"] == "2", "dteday"] = valid_day
    path = tmp_path / "control.csv"
    frame.to_csv(path, index=False)
    assert len(load_data(path)) == 6
