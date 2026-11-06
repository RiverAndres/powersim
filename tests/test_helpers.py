import pandas as pd
import pytest

from powersim.utils.helpers import calculate_time_deltas


@pytest.mark.parametrize(("freq", "expected"), [("1h", 1.0), ("15min", 0.25)])
def test_regular_index(freq, expected):
    index = pd.date_range("2025-01-01", periods=5, freq=freq, tz="UTC").tolist()
    assert set(calculate_time_deltas(index).values()) == {expected}


def test_last_period_reuses_previous_delta():
    index = pd.to_datetime(
        ["2025-01-01 00:00", "2025-01-01 01:00", "2025-01-01 01:15"], utc=True
    ).tolist()
    deltas = calculate_time_deltas(index)
    assert list(deltas.values()) == [1.0, 0.25, 0.25]
