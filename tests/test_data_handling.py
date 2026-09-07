import csv
from pathlib import Path

import pytest

from keeks_elote.data_handling import load_csv, load_dataframe, prepare_data

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class _FakeDataFrame:
    """The slice of the pandas DataFrame contract ``load_dataframe`` relies on."""

    def __init__(self, columns, records):
        self.columns = columns
        self._records = records

    def to_dict(self, orient):
        assert orient == "records"
        return self._records


def test_prepare_data_passthrough():
    """Well-formed data is returned unchanged (same object)."""
    test_data = {1: [{"winner": "A", "loser": "B"}], 2: [{"winner": "C", "loser": "D"}]}
    prepared = prepare_data(test_data)
    assert prepared == test_data
    assert id(prepared) == id(test_data)  # No copy when nothing is dropped.


def test_prepare_data_empty():
    """An empty dict passes through unchanged."""
    test_data = {}
    prepared = prepare_data(test_data)
    assert prepared == test_data
    assert id(prepared) == id(test_data)


@pytest.mark.parametrize("bad_input", [[], "not a dict", None, 42])
def test_prepare_data_non_dict_raises(bad_input):
    """Non-dict input raises a clear TypeError."""
    with pytest.raises(TypeError):
        prepare_data(bad_input)


@pytest.mark.parametrize(("games", "type_name"), [(None, "NoneType"), (42, "int"), ("not-games", "str")])
def test_prepare_data_non_list_period_raises(games, type_name):
    """Period values that are not lists raise a clear TypeError."""
    with pytest.raises(TypeError, match=rf"period 1 .* list of games, got {type_name}"):
        prepare_data({1: games})


def test_prepare_data_drops_games_missing_labels(mocker):
    """Games missing winner/loser are dropped with a warning; valid ones remain."""
    mock_logger = mocker.patch("keeks_elote.data_handling.logger")
    test_data = {
        1: [
            {"winner": "A", "loser": "B"},
            {"winner": "C"},  # missing loser
            {"loser": "E"},  # missing winner
            {"winner": None, "loser": "F"},  # explicit None
        ],
        2: [{"winner": "G", "loser": "H"}],
    }
    prepared = prepare_data(test_data)
    assert prepared == {
        1: [{"winner": "A", "loser": "B"}],
        2: [{"winner": "G", "loser": "H"}],
    }
    assert id(prepared) != id(test_data)  # A cleaned copy was built.
    assert mock_logger.warning.call_count == 3


def test_prepare_data_drops_non_dict_games():
    """Game entries that are not dicts are dropped."""
    test_data = {1: [{"winner": "A", "loser": "B"}, "garbage", None]}
    prepared = prepare_data(test_data)
    assert prepared == {1: [{"winner": "A", "loser": "B"}]}


def test_load_csv_builds_period_keyed_dict_from_fixture():
    """Required columns parse to GameRecord records; optional cells left empty are omitted; extra columns pass through."""
    loaded = load_csv(FIXTURES_DIR / "games.csv")
    assert loaded == {
        1: [
            {
                "period": 1,
                "date": "2023-08-11",
                "winner": "Alpha",
                "loser": "Beta",
                "winner_odds": 2.5,
                "loser_odds": 1.6,
                "winner_score": 3.0,
                "loser_score": 1.0,
            },
            {
                "period": 1,
                "date": "2023-08-12",
                "winner": "Gamma",
                "loser": "Delta",
                "winner_odds": 1.9,
                "loser_odds": 1.95,
                "loser_score": 2.0,
            },
        ],
        2: [
            {"period": 2, "date": "2023-08-13", "winner": "Beta", "loser": "Gamma"},
            {
                "period": 2,
                "date": "2023-08-19",
                "winner": "Delta",
                "loser": "Alpha",
                "winner_odds": 2.2,
                "loser_odds": 1.7,
                "winner_score": 1.0,
                "loser_score": 4.0,
            },
        ],
    }
    assert all(isinstance(period, int) for period in loaded)


def test_load_csv_output_is_prepare_data_ready():
    """The loader's output is the shape prepare_data consumes -- it passes through unchanged."""
    loaded = load_csv(FIXTURES_DIR / "games.csv")
    assert prepare_data(loaded) == loaded


def test_load_csv_accepts_string_paths():
    loaded = load_csv(str(FIXTURES_DIR / "games.csv"))
    assert loaded == load_csv(FIXTURES_DIR / "games.csv")


def test_load_csv_drops_malformed_rows_with_warning(mocker):
    """Rows without labels are dropped; rows with unparseable optional numbers lose just that field."""
    mock_logger = mocker.patch("keeks_elote.data_handling.logger")
    loaded = load_csv(FIXTURES_DIR / "games_malformed.csv")
    assert loaded == {
        1: [
            {"period": 1, "winner": "Alpha", "loser": "Beta", "winner_odds": 2.5, "loser_odds": 1.6},
            {"period": 1, "winner": "Delta", "loser": "Epsilon", "loser_odds": 1.7},
        ],
        2: [{"period": 2, "winner": "Zeta", "loser": "Theta", "winner_odds": 2.2}],
    }
    # Two rows dropped for missing labels, two fields dropped for unparseable numbers.
    assert mock_logger.warning.call_count == 4


@pytest.mark.parametrize(
    ("fixture_name", "message"),
    [("games_bad_period.csv", "period is missing"), ("games_non_integer_period.csv", "period must be an integer")],
)
def test_load_csv_unplaceable_period_raises(fixture_name, message):
    """A row whose period cannot be parsed fails loudly instead of silently vanishing from the schedule."""
    with pytest.raises(ValueError, match=message):
        load_csv(FIXTURES_DIR / fixture_name)


def test_load_csv_missing_required_column_raises(tmp_path):
    path = tmp_path / "no_winner.csv"
    path.write_text("period,loser\n1,Gamma\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"missing required column\(s\) winner"):
        load_csv(path)


def test_load_dataframe_matches_load_csv():
    """Both loaders agree on the same input rows."""
    with open(FIXTURES_DIR / "games.csv", newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    df = _FakeDataFrame(records[0].keys(), records)
    assert load_dataframe(df) == load_csv(FIXTURES_DIR / "games.csv")


def test_load_dataframe_treats_nan_and_none_as_absent():
    nan = float("nan")
    df = _FakeDataFrame(
        ["period", "winner", "loser", "winner_odds", "loser_odds"],
        [
            {"period": 1, "winner": "Alpha", "loser": "Beta", "winner_odds": 2.5, "loser_odds": None},
            {"period": 1, "winner": nan, "loser": "Gamma", "winner_odds": 2.0, "loser_odds": 1.8},
            {"period": 2, "winner": "Delta", "loser": "Epsilon", "winner_odds": None, "loser_odds": nan},
        ],
    )
    assert load_dataframe(df) == {
        1: [{"period": 1, "winner": "Alpha", "loser": "Beta", "winner_odds": 2.5}],
        2: [{"period": 2, "winner": "Delta", "loser": "Epsilon"}],
    }


def test_load_dataframe_missing_required_column_raises():
    df = _FakeDataFrame(["period", "winner"], [{"period": 1, "winner": "Alpha"}])
    with pytest.raises(ValueError, match=r"missing required column\(s\) loser"):
        load_dataframe(df)


def test_load_dataframe_bad_period_raises():
    df = _FakeDataFrame(["period", "winner", "loser"], [{"period": "soon", "winner": "Alpha", "loser": "Beta"}])
    with pytest.raises(ValueError, match="period must be an integer"):
        load_dataframe(df)


def test_load_dataframe_with_real_pandas():
    """The same contract against real pandas, for environments that have it (the floor CI job does not)."""
    pandas = pytest.importorskip("pandas")
    df = pandas.DataFrame(
        {
            "period": [1, 1, 2],
            "winner": ["Alpha", pandas.NA, "Delta"],
            "loser": ["Beta", "Gamma", "Epsilon"],
            "winner_odds": [2.5, 2.0, float("nan")],
        }
    )
    assert load_dataframe(df) == {
        1: [{"period": 1, "winner": "Alpha", "loser": "Beta", "winner_odds": 2.5}],
        2: [{"period": 2, "winner": "Delta", "loser": "Epsilon"}],
    }
