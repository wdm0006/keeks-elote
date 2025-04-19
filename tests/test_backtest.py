import pytest
from keeks.bankroll import BankRoll
from keeks.binary_strategies.base import BaseStrategy

from keeks_elote import Backtest

# --- Fixtures ---


@pytest.fixture
def mock_arena(mocker):
    """Fixture for a mocked elote Arena."""
    arena = mocker.Mock(name="MockArena")

    # Simple probability function for testing
    # P(A wins) = 0.6, P(B wins) = 0.4, P(C wins) = ? (assume 0.5 vs others)
    def expected_score_side_effect(p1, p2):
        if p1 == "A":
            return 0.6
        if p1 == "B":
            return 0.4
        if p1 == "C":
            return 0.5  # Assuming C is average
        return 0.5  # Default

    arena.expected_score.side_effect = expected_score_side_effect
    arena.tournament = mocker.Mock()
    return arena


@pytest.fixture
def mock_bankroll(mocker):
    """Fixture for a mocked keeks BankRoll."""
    bankroll = mocker.Mock(spec=BankRoll)
    bankroll.total_funds = 1000.0
    bankroll.percent_bettable = 1.0  # Assume 100% bettable for mock simplicity
    bankroll.win_bet = mocker.Mock(
        side_effect=lambda amount, payoff: setattr(bankroll, "total_funds", bankroll.total_funds + amount * payoff)
    )
    bankroll.lose_bet = mocker.Mock(
        side_effect=lambda amount: setattr(bankroll, "total_funds", bankroll.total_funds - amount)
    )
    return bankroll


@pytest.fixture
def mock_strategy(mocker):
    """Fixture for a mocked keeks Strategy.
    Mocks the evaluate method. Does NOT hold bankroll.
    """
    strategy = mocker.Mock(spec=BaseStrategy)
    # Assume evaluate returns a fixed fraction for simplicity in testing flow
    strategy.evaluate = mocker.Mock(return_value=0.1)  # Returns 10% bet fraction
    # Remove bankroll association
    # strategy.bankroll = mock_bankroll
    return strategy


@pytest.fixture
def mock_prepare_data(mocker):
    """Fixture to mock prepare_data, returning data unchanged."""
    # Patch in the correct location
    return mocker.patch("keeks_elote.backtest.prepare_data", side_effect=lambda x: x)


@pytest.fixture
def mock_calculate_probabilities(mocker):
    """Fixture to mock calculate_probabilities."""

    def side_effect_func(arena, game):
        # Use the arena's mock directly
        return arena.expected_score(game.get("winner"), game.get("loser"))

    # Patch in the correct location
    return mocker.patch("keeks_elote.backtest.calculate_probabilities", side_effect=side_effect_func)


@pytest.fixture
def sample_data_american_odds():
    """Sample data for backtesting with American odds."""
    return {
        1: [
            {"winner": "A", "loser": "B"},  # Game for rating update period 1
        ],
        2: [
            # Game outcome for period 2, used for rating update
            {"winner": "C", "loser": "B", "winner_odds": 150, "loser_odds": -170},
        ],
        3: [
            # Game outcome for period 3, used for rating update
            {"winner": "A", "loser": "C", "winner_odds": -200, "loser_odds": 180}
        ],
        4: [],  # No games in period 4
    }


# Helper to convert American to Decimal for payoff calculation in tests
def american_to_decimal(american_odds: float) -> float:
    if american_odds >= 0:
        return (american_odds / 100.0) + 1.0
    else:
        return (100.0 / abs(american_odds)) + 1.0


# --- Test Class ---


class TestBacktest:
    def test_init(self, mock_arena):
        """Tests Backtest initialization."""
        bt = Backtest(mock_arena)
        assert bt._arena == mock_arena

    def test_run_explicit_flow(
        self,
        mock_arena,
        mock_strategy,
        mock_bankroll,
        mock_prepare_data,
        mock_calculate_probabilities,
        sample_data_american_odds,
        mocker,
    ):
        """Tests the refactored flow of run_explicit."""
        bt = Backtest(mock_arena)
        start_betting_period = 1

        mocker.patch("keeks_elote.backtest.american_to_decimal", side_effect=american_to_decimal)

        # Pass mock_bankroll to the function
        returned_bankroll = bt.run_explicit(
            sample_data_american_odds,
            mock_strategy,
            mock_bankroll,  # Pass bankroll here
            period_to_start_betting=start_betting_period,
        )

        assert returned_bankroll == mock_bankroll  # Function now returns bankroll
        mock_prepare_data.assert_called_once_with(sample_data_american_odds)

        # --- Overall Assertions after Full Run ---

        # 1. Check Strategy Evaluations:
        # P1 evaluates P2 games (C vs B, B vs C)
        # P2 evaluates P3 games (A vs C, C vs A)
        # P3 evaluates P4 games (none)
        assert mock_strategy.evaluate.call_count == 4
        # Check specific calls if needed (arguments checked in previous version)
        # Signature updated: evaluate(probability)
        mock_strategy.evaluate.assert_any_call(probability=0.5)  # P1: Eval C vs B (or B vs C)
        mock_strategy.evaluate.assert_any_call(probability=0.6)  # P2: Eval A vs C
        mock_strategy.evaluate.assert_any_call(probability=0.4)  # P2: Eval C vs A

        # 2. Check Bankroll Updates (Only for non-dry-run periods: P2, P3)
        # Bet amount calculation is now internal to run_explicit
        # We just check win/loss calls
        assert mock_bankroll.win_bet.call_count == 2  # 1 win in P2, 1 win in P3
        assert mock_bankroll.lose_bet.call_count == 2  # 1 loss in P2, 1 loss in P3

        # Check specific calls made during Period 2 execution (bankroll = 1000):
        # Bet amount = 1000 * 1.0 * 0.1 = 100 (approx)
        mock_bankroll.win_bet.assert_any_call(mocker.ANY, 1.5)  # Bet on C won
        mock_bankroll.lose_bet.assert_any_call(mocker.ANY)  # Bet on B lost

        # Check specific calls made during Period 3 execution (bankroll approx 1050):
        # Bet amount = 1050 * 1.0 * 0.1 = 105 (approx)
        mock_bankroll.win_bet.assert_any_call(mocker.ANY, 0.5)  # Bet on A won
        mock_bankroll.lose_bet.assert_any_call(mocker.ANY)  # Bet on C lost

        # 3. Check Arena Updates (Should happen for P1, P2, P3)
        assert mock_arena.tournament.call_count == 3
        mock_arena.tournament.assert_any_call([("A", "B")])  # P1
        mock_arena.tournament.assert_any_call([("C", "B")])  # P2
        mock_arena.tournament.assert_any_call([("A", "C")])  # P3

    def test_run_explicit_no_odds(
        self, mock_arena, mock_strategy, mock_bankroll, mock_prepare_data, mock_calculate_probabilities
    ):
        """Tests run_explicit when a game in the next period lacks odds."""
        bt = Backtest(mock_arena)
        data = {
            1: [],  # Current period games
            2: [{"winner": "A", "loser": "B"}],  # Next period game without odds
        }

        # Pass mock_bankroll
        bt.run_explicit(data, mock_strategy, mock_bankroll, period_to_start_betting=0)

        # Should not call strategy evaluate if odds are missing
        mock_calculate_probabilities.assert_not_called()
        mock_strategy.evaluate.assert_not_called()
        # Bankroll win/loss methods should not be called
        # get_bet_amount is no longer called directly
        mock_bankroll.win_bet.assert_not_called()
        mock_bankroll.lose_bet.assert_not_called()

    # test_run_and_project doesn't interact with keeks strategies/bankroll, so it
    # likely doesn't need changes, but we should ensure mocks are correct.
    def test_run_and_project(
        self, mock_arena, mock_prepare_data, mock_calculate_probabilities, sample_data_american_odds, mocker
    ):
        """Tests the run_and_project method (should be unaffected by keeks changes)."""
        bt = Backtest(mock_arena)
        mock_logger = mocker.patch("keeks_elote.backtest.logger")

        bt.run_and_project(sample_data_american_odds)

        mock_prepare_data.assert_called_once_with(sample_data_american_odds)

        # Check tournament calls for each period
        assert mock_arena.tournament.call_count == 3
        mock_arena.tournament.assert_any_call([("A", "B")])
        mock_arena.tournament.assert_any_call([("C", "B")])
        mock_arena.tournament.assert_any_call([("A", "C")])

        # Check probability calculations for projections
        # Period 1 projects Period 2: C vs B
        # Period 2 projects Period 3: A vs C
        # Period 3 projects Period 4: (none)
        assert mock_calculate_probabilities.call_count == 2
        mock_calculate_probabilities.assert_any_call(mock_arena, sample_data_american_odds[2][0])  # C vs B
        mock_calculate_probabilities.assert_any_call(mock_arena, sample_data_american_odds[3][0])  # A vs C

        # Check logging output for predictions
        # P(C vs B) = arena(C, B) = 0.5 -> Predict C over B: 0.5000 (or B over C: 0.5000)
        # P(A vs C) = arena(A, C) = 0.6 -> Predict A over C: 0.6000
        # The logger might log either C or B if prob is 0.5, let's check for A vs C
        mock_logger.info.assert_any_call(f"Predicted A over C: {0.6:.4f}")
        # We can be more specific about the 0.5 case if needed
        # Example: check that one of the 0.5 predictions was logged
        found_coin_flip_log = False
        for call in mock_logger.info.call_args_list:
            args, _ = call
            if "Predicted C over B: 0.5000" in args[0] or "Predicted B over C: 0.5000" in args[0]:
                found_coin_flip_log = True
                break
        assert found_coin_flip_log, "Expected log for 0.5 probability prediction not found"
