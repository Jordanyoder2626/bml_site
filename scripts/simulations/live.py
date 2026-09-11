"""Current-lineup forecasts: actual points plus time-weighted remaining points."""

import requests


def remaining_fraction(status: dict) -> float:
    game_type = status['type']
    if game_type.get('completed') or game_type['state'] == 'post':
        return 0.0
    if game_type['state'] == 'pre':
        return 1.0
    if game_type['state'] != 'in':
        raise ValueError(f'Unsupported NFL game status: {game_type}')
    period = int(status['period'])
    clock = float(status['clock'])
    # Overtime retains scoring potential until ESPN marks the game final.
    seconds = (4 - period) * 900 + clock if period <= 4 else clock
    return min(1.0, max(0.0, seconds / 3600))


def load_game_progress(season: int, week: int) -> dict:
    response = requests.get(
        f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}',
        params={'view': 'proTeamSchedules_wl'}, timeout=30
    )
    response.raise_for_status()
    teams = response.json()['settings']['proTeams']
    progress = {}
    games = {}
    for team in teams:
        if team['id'] == 0:
            continue
        scheduled = team.get('proGamesByScoringPeriod', {}).get(str(week), [])
        if not scheduled:
            if team.get('byeWeek') == week:
                progress[team['id']] = 0.0
            continue
        if len(scheduled) != 1:
            raise ValueError('Expected one NFL game per team per scoring week')
        game = scheduled[0]
        game_id = game['id']
        if game_id not in games:
            if game.get('statsOfficial'):
                games[game_id] = 0.0
            else:
                response = requests.get(
                    'https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/'
                    f'events/{game_id}/competitions/{game_id}/status', timeout=30
                )
                response.raise_for_status()
                games[game_id] = remaining_fraction(response.json())
        progress[team['id']] = games[game_id]
    if not progress:
        raise ValueError(f'No NFL game progress found for {season} week {week}')
    return progress


def build_live_lineups(week_data, projections, progress, season, week):
    forecasts = {int(p['espn_id']): float(p['projection']) for p in projections}
    lineups = {}
    for team in week_data['teams']:
        lineup = {}
        for entry in team['roster']['entries']:
            # Bench and injured reserve cannot contribute to the matchup score.
            if entry['lineupSlotId'] in (20, 21):
                continue
            player = entry['playerPoolEntry']['player']
            pro_team = player.get('proTeamId', 0)
            if pro_team and pro_team not in progress:
                raise ValueError(f"Missing NFL status for {player['fullName']}")
            remaining = progress.get(pro_team, 0.0)
            stats = [s for s in player.get('stats', [])
                     if s.get('seasonId') == season and s.get('scoringPeriodId') == week
                     and s.get('statSplitTypeId', 1) == 1]
            actual = next((float(s['appliedTotal']) for s in stats
                           if s.get('statSourceId') == 0), 0.0)
            baseline = forecasts.get(entry['playerId'])
            if baseline is None:
                baseline = next((float(s['appliedTotal']) for s in stats
                                 if s.get('statSourceId') == 1), 0.0)
            position = {1: 'QB', 2: 'RB', 3: 'WR', 4: 'TE', 5: 'K', 16: 'DST'}.get(
                player.get('defaultPositionId'), 'UNKNOWN'
            )
            lineup[entry['playerId']] = {
                'player_name': player['fullName'], 'position': position,
                'projection': baseline, 'actual': actual if remaining < 1 else 0.0,
                'remaining_fraction': remaining, 'played': remaining == 0,
            }
        lineups[team['id']] = lineup
    return lineups
