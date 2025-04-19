import pytest

from keeks_elote.model_evaluation import calculate_probabilities


@pytest.fixture
def mock_arena(mocker):
    """Fixture for a mocked elote Arena."""
    arena = mocker.Mock()
    # Configure the mock's expected_score method
    arena.expected_score.side_effect = lambda p1, p2: 0.75 if p1 == "A" else 0.25
    return arena


def test_calculate_probabilities(mock_arena):
    """Tests the calculate_probabilities function."""
    game_a_wins = {"winner": "A", "loser": "B"}
    prob_a = calculate_probabilities(mock_arena, game_a_wins)
    mock_arena.expected_score.assert_called_once_with("A", "B")
    assert prob_a == 0.75

    mock_arena.reset_mock()  # Reset call counts for the next assertion

    game_b_wins = {"winner": "B", "loser": "A"}
    prob_b = calculate_probabilities(mock_arena, game_b_wins)
    mock_arena.expected_score.assert_called_once_with("B", "A")
    assert prob_b == 0.25


def test_calculate_probabilities_logging(mock_arena, mocker):
    """Tests the logging within calculate_probabilities."""
    mock_logger = mocker.patch("keeks_elote.model_evaluation.logger")
    game = {"winner": "X", "loser": "Y"}
    # Configure mock arena for this specific game if needed, though default works
    mock_arena.expected_score.side_effect = lambda p1, p2: 0.6

    calculate_probabilities(mock_arena, game)

    mock_logger.debug.assert_any_call("Calculating expected score for X vs Y.")
    mock_logger.debug.assert_any_call("Expected score (P(X)) = 0.6000")
