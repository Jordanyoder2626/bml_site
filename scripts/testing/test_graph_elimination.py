import unittest

from scripts.utils.league_rules import eliminated_from_postseason


class GraphEliminationTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {'team': team, 'wins': wins, 'score': 1000 - index}
            for index, (team, wins) in enumerate([
                ('Cade', 9), ('Chase', 8), ('Landry', 7), ('Leighton', 6),
                ('Caden', 5), ('Quinn', 4), ('Jordan', 3), ('Tripp', 2),
                ('Rendle', 1), ('Luke', 0),
            ])
        ]

    def test_playoff_elimination(self):
        self.assertTrue(eliminated_from_postseason(self.records, 'Luke', 1))
        self.assertFalse(eliminated_from_postseason(self.records, 'Caden', 1))

    def test_bowl_elimination(self):
        self.assertTrue(eliminated_from_postseason(self.records, 'Cade', 1, bootyman=True))
        self.assertFalse(eliminated_from_postseason(self.records, 'Luke', 1, bootyman=True))

    def test_possible_points_tie_is_not_elimination(self):
        self.assertFalse(eliminated_from_postseason(self.records, 'Tripp', 1, bootyman=True))

    def test_final_standings_use_actual_points(self):
        self.assertTrue(eliminated_from_postseason(self.records, 'Tripp', 0, bootyman=True))
        self.assertFalse(eliminated_from_postseason(self.records, 'Luke', 0, bootyman=True))


if __name__ == '__main__':
    unittest.main()
