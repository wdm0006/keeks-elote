import pytest

from keeks_elote.data_handling import prepare_data


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
