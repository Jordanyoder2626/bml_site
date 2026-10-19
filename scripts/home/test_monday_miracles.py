import unittest

from scripts.home.monday_miracles import build_monday_miracles, current_week_matchups


class MondayMiraclesTests(unittest.TestCase):
    def test_current_scores_override_zero_matchup_totals(self):
        week_data = {'schedule': [
            {'matchupPeriodId': 6,
             'home': {'teamId': 12, 'totalPoints': 0,
                      'pointsByScoringPeriod': {'6': 77.14}},
             'away': {'teamId': 2, 'totalPoints': 0,
                      'pointsByScoringPeriod': {'6': 67.88}}},
            {'matchupPeriodId': 5},
            {'matchupPeriodId': 6, 'home': {'teamId': 1}},
        ]}
        self.assertEqual(current_week_matchups(week_data, 6), [
            {'team1': 12, 'score1': 77.14, 'team2': 2, 'score2': 67.88}
        ])

    def test_final_totals_are_used_when_period_scores_are_missing(self):
        self.assertEqual(current_week_matchups({'schedule': [
            {'matchupPeriodId': 6,
             'home': {'teamId': 1, 'totalPoints': 80},
             'away': {'teamId': 2, 'totalPoints': 100}}
        ]}, 6)[0]['score1'], 80)

    def scenarios(self, own, other=(), probability=0.2, scores=(80, 100)):
        def lineup(names):
            return {i: {'player_name': name, 'remaining_fraction': remaining}
                    for i, (name, remaining) in enumerate(names)}

        return build_monday_miracles(
            [{'team1': 1, 'team2': 2, 'score1': scores[0], 'score2': scores[1]}],
            {1: lineup(own), 2: lineup(other)}, {1: probability, 2: 0.8},
            lambda team: f'Team {team}'
        )

    def test_single_player_excludes_finished_starters(self):
        rows = self.scenarios([('Alex', 1), ('Finished', 0)])
        self.assertEqual(rows[0]['requirement'],
                         'Alex needs more than 20.00 points to win.')

    def test_combined_points_and_three_names(self):
        rows = self.scenarios([('Alex', 1), ('Blake', 1), ('Casey', 1)])
        self.assertEqual(rows[0]['requirement'],
                         'Alex, Blake, and Casey need more than 20.00 combined points to win.')

    def test_live_players_need_additional_margin(self):
        rows = self.scenarios([('Alex', 0.5), ('Blake', 1)],
                              [('Will', 0.5), ('Vic', 1)], scores=(99.99, 100))
        self.assertEqual(rows[0]['requirement'],
                         'Alex and Blake need to outscore Will and Vic by more than 0.01 points to win.')

    def test_no_chance_tied_and_finished_matchups_are_excluded(self):
        self.assertEqual(self.scenarios([('Alex', 1)], probability=0), [])
        self.assertEqual(self.scenarios([('Alex', 1)], scores=(100, 100)), [])
        self.assertEqual(self.scenarios([('Alex', 0)]), [])

    def test_away_team_is_trailing(self):
        rows = self.scenarios([('Alex', 1)], [('Will', 1)], scores=(100, 80))
        self.assertEqual(rows[0]['team'], 'Team 2')
        self.assertEqual(rows[0]['requirement'],
                         'Will needs to outscore Alex by more than 20.00 points to win.')

    def test_only_opponent_can_still_score(self):
        rows = self.scenarios([], [('Will', 1)])
        self.assertIn('Will to lose more than 20.00 points', rows[0]['requirement'])


if __name__ == '__main__':
    unittest.main()
