import unittest
from unittest.mock import patch

from scripts.simulations.simulations import get_week_projections


class ESPNProjectionTests(unittest.TestCase):
    @patch('scripts.simulations.simulations.DataLoader')
    def test_weekly_league_scoring_and_direct_ids(self, loader):
        def stat(season, week, source, total):
            return {'seasonId': season, 'scoringPeriodId': week,
                    'statSourceId': source, 'statSplitTypeId': 1,
                    'appliedTotal': total, 'stats': {'53': 4.5}}

        loader.return_value.players_info.return_value = {'players': [
            {'player': {'id': 123, 'fullName': "Test O'Player",
                        'defaultPositionId': 2, 'stats': [
                            stat(2025, 7, 1, 90), stat(2026, 0, 1, 300),
                            stat(2026, 6, 1, 80), stat(2026, 7, 0, 70),
                            stat(2026, 7, 1, 18.75)]}},
            {'player': {'id': -1, 'fullName': 'Test Defense',
                        'defaultPositionId': 16,
                        'stats': [stat(2026, 7, 1, 6)]}},
            {'player': {'id': 456, 'fullName': 'No weekly projection',
                        'defaultPositionId': 3,
                        'stats': [stat(2026, 0, 1, 250)]}},
        ]}
        result = get_week_projections(week=7, season=2026).set_index('espn_id')
        loader.assert_called_once_with(year=2026, week=7)
        self.assertEqual(set(result.index), {123, -1})
        self.assertEqual(result.loc[123, 'fpts'], 18.75)
        self.assertEqual(result.loc[123, 'rec'], 4.5)
        self.assertEqual(result.loc[123, 'id'], 'TestOPlayer_2026_07')
        self.assertEqual(result.loc[-1, 'position'], 'DST')

    @patch('scripts.simulations.simulations.DataLoader')
    def test_missing_weekly_projections_stop_import(self, loader):
        loader.return_value.players_info.return_value = {'players': []}
        with self.assertRaisesRegex(RuntimeError, 'season 2026, week 7'):
            get_week_projections(week=7, season=2026)

    @patch('databases.updates.betting_table.simulations')
    def test_betting_fallback_uses_named_columns(self, simulations):
        import pandas as pd
        from databases.updates.betting_table import _load_projections

        simulations.query_projections_db.return_value = pd.DataFrame()
        simulations.get_week_projections.return_value = pd.DataFrame([
            {'espn_id': 123, 'fpts': 18.75, 'player': 'Test Player', 'rec': 4.5}
        ])
        result = _load_projections(season=2026, week=7)
        simulations.get_week_projections.assert_called_once_with(week=7, season=2026)
        self.assertEqual(result[0]['projection'], 18.75)
        self.assertEqual(result[0]['name'], 'Test Player')


if __name__ == '__main__':
    unittest.main()
