from keeks import Opportunity


class Backtest:
    def __init__(self, arena):
        self._arena = arena

    def run_explicit(self, data, strategy, period_to_start_betting=3):
        """
        Takes in data of the schema:

        {
            period: [
                {
                    "winner": label,
                    "loser": label,
                    "winner_odds": float,
                    "loser_odds": float
                },
                ...
            ],
            ...
        }

        Where period is a monotonically increasing integer. Odds are optional, if not passed then the game will just be
        used for rating.

        :param data:
        :return:
        """

        for week_no, games in data.items():
            print('\nrunning with week %s' % (week_no,))
            opps = []
            for game in data.get(week_no + 1, []):
                if 'winner_odds' in game.keys():
                    prob_win = self._arena.expected_score(game.get('winner'), game.get('loser'))
                    opps.append(Opportunity(
                        game.get('winner'),
                        game.get('loser'),
                        probability=prob_win,
                        odds=game.get('winner_odds'),
                        verbose=1,
                        truth=True
                    ))

                    prob_win = self._arena.expected_score(game.get('loser'), game.get('winner'))
                    opps.append(Opportunity(
                        game.get('loser'),
                        game.get('winner'),
                        probability=prob_win,
                        odds=game.get('loser_odds'),
                        verbose=1,
                        truth=False
                    ))
            # after week a while we start betting
            if week_no > period_to_start_betting:
                strategy.evaluate_and_issue(opps)
                print('bankroll: %s' % (strategy.total_funds,))
            else:
                print('dry run week, no actual bets issued')
                strategy.evaluate_and_issue(opps, dry_run=True)

            matchups = [(x.get('winner'), x.get('loser')) for x in games]
            self._arena.tournament(matchups)

        return strategy

    def run_and_project(self, data):
        for week_no, games in data.items():
            print('\nrunning with week %s' % (week_no,))
            matchups = [(x.get('winner'), x.get('loser')) for x in games]
            self._arena.tournament(matchups)

            for game in data.get(week_no + 1, []):
                prob_win = self._arena.expected_score(game.get('winner'), game.get('loser'))
                if prob_win > 0.5:
                    print('Predicted %s over %s: %s' % (game.get('winner'), game.get('loser'), prob_win, ))
                else:
                    print('Predicted %s over %s: %s' % (game.get('loser'), game.get('winner'), prob_win, ))
