from keeks_elote.data_handling import prepare_data


def test_prepare_data_passthrough():
    """Tests that prepare_data currently returns the input data unchanged."""
    test_data = {1: [{"winner": "A", "loser": "B"}], 2: [{"winner": "C", "loser": "D"}]}
    prepared = prepare_data(test_data)
    assert prepared == test_data
    assert id(prepared) == id(test_data)  # Ensure it's the same object for now


def test_prepare_data_empty():
    """Tests prepare_data with empty input."""
    test_data = {}
    prepared = prepare_data(test_data)
    assert prepared == test_data


def test_prepare_data_different_types(mocker):
    """Tests prepare_data logs correctly for different input types (though it only expects dict)."""
    mock_logger = mocker.patch("keeks_elote.data_handling.logger")

    prepare_data([])
    mock_logger.debug.assert_any_call("Input data type: <class 'list'>")

    prepare_data({1: []})
    mock_logger.debug.assert_any_call("Input data type: <class 'dict'>")
    mock_logger.debug.assert_any_call("Data has 1 periods.")
