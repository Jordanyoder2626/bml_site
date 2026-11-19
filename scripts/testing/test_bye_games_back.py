import unittest

from scripts.utils import league_rules


class ByeGamesBackTests(unittest.TestCase):
    def setUp(self):
        # West has the stronger records; the East winner still earns a bye.
        self.records = [
            {'team': team, 'wins': wins, 'score': score}
            for team, wins, score in [
                ('Tripp', 9, 1000), ('Chase', 8, 950), ('Cade', 7, 900),
                ('Landry', 6, 850), ('Leighton', 5, 800),
                ('Caden', 5, 950), ('Quinn', 4, 900), ('Jordan', 3, 850),
                ('Rendle', 2, 800), ('Luke', 1, 750),
            ]
        ]

    def test_division_leader_is_ahead_despite_lower_record(self):
        self.assertEqual(league_rules.bye_games_back(self.records, 'Caden'), -1)

    def test_chaser_can_take_division_title_instead_of_wildcard_bye(self):
        self.assertEqual(league_rules.bye_games_back(self.records, 'Quinn'), 1)

    def test_wildcard_route_is_closer_for_strong_division(self):
        self.assertEqual(league_rules.bye_games_back(self.records, 'Cade'), 1)
        self.assertEqual(league_rules.bye_games_back(self.records, 'Chase'), -1)

    def test_two_seven_win_bye_holders_have_one_game_cushion(self):
        records = [
            {'team': team, 'wins': wins, 'score': score}
            for team, wins, score in [
                ('Cade', 7, 1092), ('Quinn', 6, 1043), ('Chase', 7, 1000),
                ('Landry', 6, 1035), ('Jordan', 4, 969), ('Leighton', 4, 917),
                ('Tripp', 3, 1032), ('Luke', 3, 983), ('Rendle', 3, 915),
                ('Caden', 2, 940),
            ]
        ]
        self.assertEqual(league_rules.bye_games_back(records, 'Cade'), -1)
        self.assertEqual(league_rules.bye_games_back(records, 'Chase'), -1)
        self.assertEqual(league_rules.bye_games_back(records, 'Landry'), 1)

    def test_division_title_can_clinch_a_bye(self):
        self.assertEqual(league_rules.bye_status(self.records, 'Caden', 0), 'c')
        self.assertEqual(league_rules.bye_status(self.records, 'Quinn', 0), 'x')
        self.assertIsNone(league_rules.bye_status(self.records, 'Quinn', 1))

    def test_points_tie_is_unresolved_before_final_week(self):
        self.assertIsNone(league_rules.bye_status(self.records, 'Caden', 1))

    def test_clinched_division_is_not_eliminated_by_wildcard_cutoff(self):
        records = [dict(row, wins=7) if row['team'] == 'Caden' else row.copy()
                   for row in self.records]
        self.assertEqual(league_rules.bye_status(records, 'Caden', 2), 'c')

    def test_rivals_cannot_both_win_their_head_to_head_game(self):
        records = [
            {'team': team, 'wins': wins, 'score': 1000}
            for team, wins in [
                ('Tripp', 8), ('Chase', 8), ('Quinn', 8), ('Caden', 6),
                ('Cade', 5), ('Landry', 5),
            ]
        ]
        matchups = [('Tripp', 'Chase'), ('Quinn', 'Caden'), ('Cade', 'Landry')]
        clinched, eliminated = league_rules.scheduled_postseason_status(records, matchups, 5)
        self.assertIn('Caden', clinched)
        self.assertNotIn('Cade', eliminated)
        self.assertNotIn('Landry', eliminated)

    def test_projected_final_result_leaves_points_tiebreaker_open(self):
        clinched, eliminated = league_rules.scheduled_postseason_status(
            self.records, [], 1, points_pending=True
        )
        self.assertIn('Tripp', clinched)
        self.assertIn('Caden', eliminated)
        tied = [dict(row, wins=9) if row['team'] == 'Chase' else row for row in self.records]
        clinched, eliminated = league_rules.scheduled_postseason_status(
            tied, [], 1, points_pending=True
        )
        self.assertNotIn('Chase', clinched)
        self.assertNotIn('Chase', eliminated)


if __name__ == '__main__':
    unittest.main()
