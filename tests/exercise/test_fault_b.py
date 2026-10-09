"""Fault B (team design): a normalised value just above the inclusive upper bound.

`temp = 1.0000001` parses as a valid float, so `load_data` accepts it and only the
range rule in `check_domains` can reject it. `temp = 1.0` is the exact upper bound:
it is valid and occurs in the canonical CSV (instant 13164), so a strict `< 1` check
would wrongly reject real data while a loose or rounded check would let the fault in.
"""

from pathlib import Path

import pandas as pd
import pytest

from bike_demand.validate import load_data

pytestmark = pytest.mark.exercise
FIXTURES = Path(__file__).parents[1] / "fixtures"
FAULT_B = FIXTURES / "temp-just-above-one.csv"


def test_fault_b_rejects_temp_just_above_one():
    before = FAULT_B.read_bytes()
    with pytest.raises(ValueError, match=r"temp: require finite normalised values"):
        load_data(FAULT_B)
    assert FAULT_B.read_bytes() == before


@pytest.mark.parametrize("bound", ["1.0", "0.0"])
def test_fault_b_controls_inclusive_bounds_are_accepted(tmp_path, bound):
    frame = pd.read_csv(FAULT_B, dtype=str)
    frame.loc[frame["instant"] == "2", "temp"] = bound
    path = tmp_path / "control.csv"
    frame.to_csv(path, index=False)
    assert len(load_data(path)) == 6
