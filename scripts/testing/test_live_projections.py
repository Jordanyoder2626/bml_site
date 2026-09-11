import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.simulations.live import build_live_lineups, remaining_fraction
from scripts.simulations.simulations import simulate_lineup, simulate_week


class LiveProjectionTests(unittest.TestCase):
    def test_game_progress(self):
        self.assertEqual(remaining_fraction({'type': {'state': 'pre'}}), 1)
        self.assertEqual(remaining_fraction({'type': {'state': 'post'}}), 0)
        self.assertEqual(remaining_fraction({
            'type': {'state': 'in'}, 'period': 2, 'clock': 0}), 0.5)
        self.assertGreater(remaining_fraction({
            'type': {'state': 'in'}, 'period': 5, 'clock': 300}), 0)

    def test_starters_actuals_and_missing_projection(self):
        def entry(player_id, slot, actual):
            return {'playerId': player_id, 'lineupSlotId': slot,
                    'playerPoolEntry': {'player': {
                        'fullName': str(player_id), 'proTeamId': player_id,
                        'defaultPositionId': 2,
                        'stats': [{'seasonId': 2026, 'scoringPeriodId': 1,
                                   'statSourceId': 0, 'appliedTotal': actual}]}}}
        data = {'teams': [{'id': 1, 'roster': {'entries': [
            entry(1, 2, 0), entry(2, 23, -2), entry(3, 20, 50),
            entry(4, 21, 50)]}}]}
        lineup = build_live_lineups(data, [], {1: 0, 2: 0}, 2026, 1)[1]
        self.assertEqual(set(lineup), {1, 2})
        self.assertEqual(simulate_lineup(lineup), -2)
        self.assertTrue(lineup[1]['played'])

    def test_live_points_are_added_once(self):
        lineup = {1: {'position': 'RB', 'projection': 20, 'actual': 12,
                      'played': False, 'remaining_fraction': 0.5}}
        with patch('scripts.simulations.simulations.st.gamma.rvs') as draw:
            draw.return_value.item.return_value = 20
            self.assertEqual(simulate_lineup(lineup), 22)
        lineup[1].update(played=True, remaining_fraction=0)
        self.assertEqual(simulate_lineup(lineup), 12)

    def test_final_ties_are_shared(self):
        player = {'position': 'RB', 'projection': 20, 'actual': 10, 'played': True}
        counts = simulate_week(
            week_data={}, teams=SimpleNamespace(team_ids=[1, 2]), rosters=None,
            params=None, replacement_players={}, matchups=[{'team1': 1, 'team2': 2}],
            projections=[], week=1, n_sims=2,
            prepared_lineups={1: {1: player}, 2: {2: player}})
        self.assertEqual(counts[0], {1: 20, 2: 20})
        for category in counts[1:]:
            self.assertEqual(category, {1: 1, 2: 1})


if __name__ == '__main__':
    unittest.main()
