import csv
import tempfile
import unittest

from scripts.simulations.leverage_odds import build_odds, odds_path, write_odds


class LeverageOddsTests(unittest.TestCase):
    def test_bootyman_uses_participation_not_playoff_flag(self):
        results = [
            {'A': {'current_week_result': outcome, 'playoffs': 0, 'bootyman': participates}}
            for outcome, participates in [(1, 0), (1, 1), (0, 1), (0, 1)]
        ]
        row = build_odds(results, ['A'], metric='bootyman')[0]
        self.assertEqual(row['current'], 75)
        self.assertEqual(row['if_win'], 50)
        self.assertEqual(row['if_loss'], 100)

    def test_bootyman_export_is_separate_from_playoffs(self):
        with tempfile.TemporaryDirectory() as root:
            results = [{'A': {'current_week_result': 0, 'playoffs': 0, 'bootyman': 1}}]
            playoff = write_odds(results, ['A'], 2026, 10, root=root)
            bootyman = write_odds(results, ['A'], 2026, 10, root=root, metric='bootyman')
            self.assertNotEqual(playoff, bootyman)
            with bootyman.open(newline='', encoding='utf-8') as source:
                self.assertEqual(float(next(csv.DictReader(source))['current']), 100)

    def test_conditional_denominators(self):
        results = [
            {'A': {'current_week_result': outcome, 'playoffs': qualified}}
            for outcome, qualified in [(1, 1), (1, 1), (1, 0), (0, 0)]
        ]
        row = build_odds(results, ['A'])[0]
        self.assertEqual(row['current'], 50)
        self.assertAlmostEqual(row['if_win'], 200 / 3)
        self.assertEqual(row['if_loss'], 0)
        self.assertEqual((row['win_samples'], row['loss_samples']), (3, 1))
        self.assertAlmostEqual((row['if_win'] * 3 + row['if_loss']) / 4, row['current'])

    def test_unobserved_loss_is_not_zero(self):
        row = build_odds([{'A': {'current_week_result': 1, 'playoffs': 1}}], ['A'])[0]
        self.assertIsNone(row['if_loss'])
        self.assertEqual(row['if_win'], 100)

    def test_absent_matchup_has_no_conditional_odds(self):
        row = build_odds([{'A': {'current_week_result': None, 'playoffs': 0}}], ['A'])[0]
        self.assertIsNone(row['if_loss'])
        self.assertIsNone(row['if_win'])

    def test_export_metadata_and_missing_probability(self):
        with tempfile.TemporaryDirectory() as root:
            result = [{'A': {'current_week_result': 1, 'playoffs': 1}}]
            path = write_odds(result, ['A'], 2026, 10, root=root)
            self.assertEqual(path, odds_path(2026, 10, root=root))
            with path.open(newline='', encoding='utf-8') as source:
                row = next(csv.DictReader(source))
            self.assertEqual(row['if_loss'], '')
            self.assertEqual(row['simulations'], '1')
            self.assertEqual((row['season'], row['week']), ('2026', '10'))
            self.assertTrue(row['generated_utc'])


if __name__ == '__main__':
    unittest.main()
