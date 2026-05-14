import json
from pathlib import Path
from datetime import datetime as dt

import pandas as pd

from scripts.api.DataLoader import DataLoader
from scripts.home.playoff_scenarios import PlayoffScenarios
from scripts.utils.database import Database
from scripts.api.Settings import Params
from scripts.api.Teams import Teams
from scripts.home.standings import Standings
from scripts.utils import constants
from scripts.utils import league_rules
import scripts.scenarios.scenarios as scenarios
from scripts.simulations import simulations
from scripts.efficiency.efficiencies import plot_efficiency


MANAGER_TO_TEAM_NAME = {
    team['name']['display']: team['name'].get('team_name', team['name']['display'])
    for team in constants.TEAM_IDS.values()
}


def display_team_name(name: str) -> str:
    return MANAGER_TO_TEAM_NAME.get(name, name)


def manager_display_name(team_id: int) -> str:
    owner_id = teams.teamid_to_primowner[team_id]
    return constants.TEAM_IDS[owner_id]['name']['display']


def team_display_name(team_id: int) -> str:
    return display_team_name(manager_display_name(team_id))


def _format_score(score) -> str:
    return f'{float(score):.2f}'


def _logo_path(manager_name: str) -> str:
    logo_dir = Path('logos')
    matches = sorted(logo_dir.glob(f'{manager_name}.*'))
    if not matches:
        exact = logo_dir / manager_name
        matches = [exact] if exact.exists() else []
    return f'logos/{matches[0].name}' if matches else ''


def _team_card_from_team_id(team_id: int) -> dict:
    manager = manager_display_name(team_id)
    return {
        'manager': manager,
        'team': team_display_name(team_id),
        'logo': _logo_path(manager)
    }


def _team_card_from_manager(manager: str) -> dict:
    return {
        'manager': manager,
        'team': display_team_name(manager),
        'logo': _logo_path(manager)
    }


def _team_id_from_manager(manager: str) -> int | None:
    for owner_id, team_id in teams.primowner_to_teamid.items():
        if constants.TEAM_IDS[owner_id]['name']['display'] == manager:
            return team_id
    return None


def _team_id_from_display_name(display_name: str) -> int | None:
    for owner_id, team_id in teams.primowner_to_teamid.items():
        manager = constants.TEAM_IDS[owner_id]['name']['display']
        if display_team_name(manager) == display_name:
            return team_id
    return None


def _matchup_score(matchup: dict, team_id: int):
    if matchup.get('team1') == team_id:
        return matchup.get('score1')
    if matchup.get('team2') == team_id:
        return matchup.get('score2')
    return None


def _display_score(score) -> str:
    if score is None:
        return ''
    try:
        if float(score) == 0:
            return ''
    except (TypeError, ValueError):
        return ''
    return _format_score(score)


def display_team_values(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    for column in columns:
        if column in df.columns:
            df[column] = df[column].map(display_team_name)
    return df


def display_team_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={
        column: display_team_name(column)
        for column in df.columns
    })


def display_team_list_rows(rows: list[list]) -> list[list]:
    return [
        [display_team_name(row[0]), *row[1:]]
        if row else row
        for row in rows
    ]


def _display_team_series(names: str) -> str:
    teams = [
        display_team_name(name.strip())
        for name in str(names).split(',')
        if name.strip()
    ]

    if len(teams) <= 1:
        return teams[0] if teams else ''
    if len(teams) == 2:
        return ' or '.join(teams)
    return f'{", ".join(teams[:-1])}, or {teams[-1]}'


def _display_team_or_series(teams: list[str]) -> str:
    display_teams = [display_team_name(team) for team in teams]

    if len(display_teams) <= 1:
        return display_teams[0] if display_teams else ''
    if len(display_teams) == 2:
        return ' or '.join(display_teams)
    return f'{", ".join(display_teams[:-1])}, or {display_teams[-1]}'


def _net_result_phrase(net_wins: int, other_teams: str, scenario_type: str) -> str:
    team_count = len([
        team
        for team in str(other_teams).split(',')
        if team.strip()
    ])
    other_teams = _display_team_series(other_teams)
    loss_phrase = 'a loss by' if team_count <= 1 else 'losses by'
    win_phrase = 'a win by' if team_count <= 1 else 'wins by'
    loses_verb = 'loses' if team_count <= 1 else 'lose'
    wins_verb = 'wins' if team_count <= 1 else 'win'

    if scenario_type == 'clinch':
        if net_wins >= 1:
            return f'with a win plus {loss_phrase} {other_teams}'
        if net_wins == 0:
            return f'by matching or better than {other_teams}'
        return f'with a loss if {other_teams} {wins_verb}'

    if net_wins >= 1:
        return f'even with a win if {other_teams} {loses_verb}'
    if net_wins == 0:
        return f'by matching or worse than {other_teams}'
    return f'with a loss plus {win_phrase} {other_teams}'


def _visible_probability(probability: str) -> bool:
    return str(probability).strip() != '0.0%'


def _team_verb(team_name: str, singular: str, plural: str) -> str:
    return plural if team_name.endswith('s') else singular


def _format_threshold_phrases(display_team: str,
                              thresholds: list[dict],
                              scenario_type: str) -> list[str]:
    phrases = []

    for threshold in thresholds:
        other_team = display_team_name(threshold['team'])
        points = f"{float(threshold['points']):.2f}"

        if threshold['direction'] == 'other_needs':
            if scenario_type == 'clinch':
                phrase = (
                    f'{display_team} must not get outscored by '
                    f'{other_team} (+{points})'
                )
            else:
                phrase = (
                    f'{other_team} needs +{points} vs {display_team} '
                    f'to keep them out'
                )
        else:
            if scenario_type == 'clinch':
                phrase = f'{display_team} must outscore {other_team} (+{points})'
            else:
                phrase = f'{display_team} needs +{points} vs {other_team} to pass'

        phrases.append(phrase)

    return phrases


def _format_tiebreaker_sentence(team: str,
                                metadata: dict | None,
                                scenario_type: str) -> str:
    if not metadata:
        return ''

    if metadata.get('type') != 'final_week_playoff_tiebreaker':
        return ''

    thresholds = metadata.get('thresholds', [])
    if not thresholds:
        return ''

    team_count = len(thresholds)
    display_team = display_team_name(team)
    other_teams = _display_team_or_series([
        threshold['team']
        for threshold in thresholds
    ])
    loses_verb = 'loses' if team_count <= 1 else 'lose'
    wins_verb = 'wins' if team_count <= 1 else 'win'
    phrases = _format_threshold_phrases(
        display_team=display_team,
        thresholds=thresholds,
        scenario_type=scenario_type
    )

    if len(phrases) == 1:
        threshold_text = phrases[0]
    else:
        threshold_text = '; '.join(phrases)

    if scenario_type == 'clinch':
        return (
            f' If {display_team} loses and {other_teams} {wins_verb}: '
            f'{threshold_text}.'
        )

    return (
        f' If {display_team} wins and {other_teams} {loses_verb}: '
        f'{threshold_text}.'
    )


def _format_bootyman_threshold_phrases(display_team: str,
                                       thresholds: list[dict],
                                       scenario_type: str) -> list[str]:
    phrases = []

    for threshold in thresholds:
        other_team = display_team_name(threshold['team'])
        points = f"{float(threshold['points']):.2f}"

        if threshold['direction'] == 'other_needs':
            if scenario_type == 'escape':
                phrase = (
                    f'{display_team} must not get outscored by '
                    f'{other_team} (+{points})'
                )
            else:
                phrase = (
                    f'{other_team} needs +{points} vs {display_team} '
                    f'to push them in'
                )
        else:
            if scenario_type == 'escape':
                phrase = f'{display_team} must outscore {other_team} (+{points})'
            else:
                phrase = (
                    f'{display_team} must outscore {other_team} (+{points}) '
                    f'to avoid it'
                )

        phrases.append(phrase)

    return phrases


def _format_bootyman_tiebreaker_sentence(team: str,
                                         metadata: dict | None,
                                         scenario_type: str) -> str:
    if not metadata:
        return ''

    if metadata.get('type') != 'final_week_bootyman_tiebreaker':
        return ''

    thresholds = metadata.get('thresholds', [])
    if not thresholds:
        return ''

    team_count = len(thresholds)
    display_team = display_team_name(team)
    other_teams = _display_team_or_series([
        threshold['team']
        for threshold in thresholds
    ])
    wins_verb = 'wins' if team_count <= 1 else 'win'
    loses_verb = 'loses' if team_count <= 1 else 'lose'
    threshold_text = '; '.join(
        _format_bootyman_threshold_phrases(
            display_team=display_team,
            thresholds=thresholds,
            scenario_type=scenario_type
        )
    )

    if scenario_type == 'escape':
        return (
            f' If {display_team} loses and {other_teams} {wins_verb}: '
            f'{threshold_text}.'
        )

    return (
        f' If {display_team} wins and {other_teams} {loses_verb}: '
        f'{threshold_text}.'
    )


def format_scenario_statements(rows: list[list], scenario_type: str) -> list[list]:
    formatted_rows = []

    for row in rows:
        if len(row) < 5:
            continue

        team, target, net_wins, other_teams = row[:4]
        metadata = row[4] if len(row) > 5 and isinstance(row[4], dict) else None
        probability = row[5] if metadata else row[4]
        if not _visible_probability(probability):
            continue

        display_team = display_team_name(team)
        verb = (
            _team_verb(display_team, 'clinches', 'clinch')
            if scenario_type == 'clinch'
            else _team_verb(display_team, 'is eliminated from', 'are eliminated from')
        )
        statement = (
            f'{display_team} {verb} {str(target).lower()} '
            f'{_net_result_phrase(int(net_wins), other_teams, scenario_type)}.'
            f'{_format_tiebreaker_sentence(team, metadata, scenario_type)}'
        )
        formatted_rows.append([statement, probability])

    return formatted_rows


def format_bootyman_scenario_statements(rows: list[list]) -> list[list]:
    formatted_rows = []

    for row in rows:
        if len(row) < 6:
            continue

        team, _, net_wins, other_teams, bootyman_type = row[:5]
        metadata = row[5] if len(row) > 6 and isinstance(row[5], dict) else None
        probability = row[6] if metadata else row[5]
        if not _visible_probability(probability):
            continue

        display_team = display_team_name(team)
        other_team_count = len([
            team_name
            for team_name in str(other_teams).split(',')
            if team_name.strip()
        ])
        other_teams = _display_team_series(other_teams)
        loss_phrase = 'a loss by' if other_team_count <= 1 else 'losses by'
        win_phrase = 'a win by' if other_team_count <= 1 else 'wins by'
        loses_verb = 'loses' if other_team_count <= 1 else 'lose'
        wins_verb = 'wins' if other_team_count <= 1 else 'win'

        if bootyman_type == 'escape':
            verb = _team_verb(display_team, 'escapes', 'escape')
            if not other_teams:
                condition = 'with a win' if int(net_wins) >= 1 else 'this week'
            elif int(net_wins) >= 1:
                condition = f'with a win plus {loss_phrase} {other_teams}'
            elif int(net_wins) == 0:
                condition = f'by matching or better than {other_teams}'
            else:
                condition = f'with a loss if {other_teams} {wins_verb}'
            statement = (
                f'{display_team} {verb} Bootyman Bowl {condition}.'
                f'{_format_bootyman_tiebreaker_sentence(team, metadata, bootyman_type)}'
            )
        else:
            verb = _team_verb(display_team, 'clinches', 'clinch')
            if not other_teams:
                condition = 'with a loss' if int(net_wins) < 0 else 'this week'
            elif int(net_wins) >= 1:
                condition = f'even with a win if {other_teams} {loses_verb}'
            elif int(net_wins) == 0:
                condition = f'by matching or worse than {other_teams}'
            else:
                condition = f'with a loss plus {win_phrase} {other_teams}'
            statement = (
                f'{display_team} {verb} Bootyman Bowl {condition}.'
                f'{_format_bootyman_tiebreaker_sentence(team, metadata, bootyman_type)}'
            )

        formatted_rows.append([statement, probability])

    return formatted_rows


def _format_matchup_record(wins: int, losses: int, ties: int) -> str:
    if ties:
        return f'{wins}-{losses}-{ties}'
    return f'{wins}-{losses}'


def build_all_time_matchups_table(matchups: pd.DataFrame) -> pd.DataFrame:
    if matchups.empty:
        return pd.DataFrame(columns=['Team'])

    matchups = matchups.copy()
    matchups = matchups[
        matchups.team.notna()
        & matchups.opponent.notna()
        & matchups.matchup_result.notna()
    ]

    if matchups.empty:
        return pd.DataFrame(columns=['Team'])

    matchups['matchup_result'] = pd.to_numeric(
        matchups.matchup_result,
        errors='coerce'
    )
    matchups = matchups.dropna(subset=['matchup_result'])

    teams = sorted(
        set(matchups.team.dropna())
        | set(matchups.opponent.dropna())
    )
    rows = []

    for team in teams:
        row = {'Team': team}
        team_games = matchups[matchups.team == team]

        for opponent in teams:
            if opponent == team:
                row[opponent] = '-'
                continue

            games = team_games[team_games.opponent == opponent]
            if games.empty:
                row[opponent] = '-'
                continue

            wins = int((games.matchup_result == 1).sum())
            losses = int((games.matchup_result == 0).sum())
            ties = int((games.matchup_result == 0.5).sum())
            row[opponent] = _format_matchup_record(wins, losses, ties)

        wins = int((team_games.matchup_result == 1).sum())
        losses = int((team_games.matchup_result == 0).sum())
        ties = int((team_games.matchup_result == 0.5).sum())
        row['Total'] = _format_matchup_record(wins, losses, ties)
        rows.append(row)

    return pd.DataFrame(rows, columns=['Team', *teams, 'Total'])


def _pair_record(matchups: pd.DataFrame, team: str, opponent: str) -> tuple[int, int, int]:
    games = matchups[
        (matchups.team == team)
        & (matchups.opponent == opponent)
    ]
    wins = int((games.matchup_result == 1).sum())
    losses = int((games.matchup_result == 0).sum())
    ties = int((games.matchup_result == 0.5).sum())
    return wins, losses, ties


def _pair_record_text(matchups: pd.DataFrame, team: str, opponent: str) -> str:
    wins, losses, ties = _pair_record(matchups, team, opponent)
    return f'{team} {_format_matchup_record(wins, losses, ties)}'


def _pair_matchup_text(matchups: pd.DataFrame, team: str, opponent: str) -> str:
    wins, _, ties = _pair_record(matchups, team, opponent)
    opponent_wins, _, _ = _pair_record(matchups, opponent, team)

    if ties:
        return f'{team} ({wins}) vs {opponent} ({opponent_wins}) - {ties} ties'
    return f'{team} ({wins}) vs {opponent} ({opponent_wins})'


def build_rivalry_record_rows(matchups: pd.DataFrame) -> pd.DataFrame:
    columns = ['category', 'record', 'holder', 'season', 'week']
    if matchups.empty:
        return pd.DataFrame(columns=columns)

    matchups = matchups.copy()
    matchups = matchups[
        matchups.team.notna()
        & matchups.opponent.notna()
        & matchups.matchup_result.notna()
    ]
    matchups = matchups[
        (matchups.team != 'Peyton')
        & (matchups.opponent != 'Peyton')
    ]
    matchups['matchup_result'] = pd.to_numeric(
        matchups.matchup_result,
        errors='coerce'
    )
    matchups = matchups.dropna(subset=['matchup_result'])

    teams = sorted(
        set(matchups.team.dropna())
        | set(matchups.opponent.dropna())
    )
    pair_rows = []

    for i, team in enumerate(teams):
        for opponent in teams[i + 1:]:
            wins, losses, ties = _pair_record(matchups, team, opponent)
            games = wins + losses + ties
            if games == 0:
                continue

            win_pct = (wins + (ties * 0.5)) / games
            opponent_win_pct = 1 - win_pct
            better_team = team if win_pct >= opponent_win_pct else opponent
            worse_team = opponent if better_team == team else team
            better_pct = max(win_pct, opponent_win_pct)

            pair_rows.append({
                'team': team,
                'opponent': opponent,
                'games': games,
                'closest_margin': abs(win_pct - 0.5),
                'better_team': better_team,
                'worse_team': worse_team,
                'better_pct': better_pct,
            })

    if not pair_rows:
        return pd.DataFrame(columns=columns)

    pairs = pd.DataFrame(pair_rows)
    closest_margin = pairs.closest_margin.min()
    closest_pairs = pairs[pairs.closest_margin == closest_margin].sort_values(
        ['games', 'team', 'opponent'],
        ascending=[False, True, True]
    )
    daddy = pairs.sort_values(
        ['better_pct', 'games'],
        ascending=[False, False]
    ).iloc[0]

    daddy_team = daddy['better_team']
    daddy_opponent = daddy['worse_team']
    closest_records = [
        _pair_matchup_text(matchups, row.team, row.opponent)
        for row in closest_pairs.itertuples()
    ]
    closest_holders = [
        f'{row.team} vs {row.opponent}'
        for row in closest_pairs.itertuples()
    ]

    rows = [
        [
            'Closest Rivalries' if len(closest_pairs) > 1 else 'Closest Rivalry',
            '<br>'.join(closest_records),
            '<br>'.join(closest_holders),
            '',
            ''
        ],
        [
            "Who's Your Daddy?",
            _pair_matchup_text(matchups, daddy_team, daddy_opponent),
            f'{daddy_team} over {daddy_opponent}',
            '',
            ''
        ],
    ]
    return pd.DataFrame(rows, columns=columns)


season = constants.SEASON
data = DataLoader(season)
params = Params(data)
teams = Teams(data)
week = params.regular_season_end+1 if params.current_week > params.regular_season_end+1 else params.current_week
previous_week = max(params.current_week - 1, 0)
power_data_week = (
    params.regular_season_end
    if params.current_week > params.regular_season_end
    else previous_week
)
power_display_week = 'Final' if params.current_week > params.regular_season_end else f'Week {week}'
n_teams = len(teams.team_ids)

# load db tables
day = dt.now().strftime('%a')
the_week = params.as_of_week if day == 'Tue' else params.current_week  # Wed is start of new week, and season_sim runs on Tue
the_week = max(the_week, 1)
completed_week = max(min(params.as_of_week, params.regular_season_end), 0)
db_pr = Database(table='power_ranks', season=season, week=power_data_week)
betting_table = (
    Database(table='betting_table', season=season, week=params.current_week)
    .retrieve_data(how='week')
    .sort_values('created')
)
if not betting_table.empty:
    betting_table = betting_table.groupby('team', as_index=False).tail(1)
season_sim_table = (
    Database(table='season_sim', season=season, week=week).
    retrieve_data(how='season')
    .sort_values('created')
    .tail(n_teams)  # most recent db updates
)
season_sim_wins_table = Database(table='season_sim_wins', season=season, week=the_week).retrieve_data(how='week')
season_sim_ranks_table = Database(table='season_sim_ranks', season=season, week=the_week).retrieve_data(how='week')
h2h_data = Database(table='h2h', season=season, week=completed_week).retrieve_data(how='season')
ss_data = Database(table='schedule_switcher', season=season, week=completed_week).retrieve_data(how='season')
alltime_df = Database(table='alltime_standings').retrieve_data(how='all')
records_df = Database(table='records').retrieve_data(how='all')
actual_matchups_df = Database(table='matchups').retrieve_data(how='all')
alltime_matchups_df = build_all_time_matchups_table(actual_matchups_df)
rivalry_records_df = build_rivalry_record_rows(actual_matchups_df)
records_df = records_df.copy()
season_record_categories = {
    'Most Wins',
    'Most Losses',
    'Highest PPG',
    'Lowest PPG',
    'Most Top Half Wins',
    'Most Top Half Losses'
}
if not records_df.empty and 'category' in records_df.columns and 'week' in records_df.columns:
    records_df.loc[
        records_df.category.isin(season_record_categories),
        'week'
    ] = ''
if not rivalry_records_df.empty:
    records_df = pd.concat([records_df, rivalry_records_df], ignore_index=True)


# HOME PAGE
standings_week = (
    params.regular_season_end
    if params.current_week > params.regular_season_end
    else week
)
standings = Standings(season=season, week=standings_week)
if params.current_week > params.regular_season_end:
    standings.params.as_of_week = params.regular_season_end
standings_df = standings.format_standings()
clinches = standings.clinching_scenarios()
ps = PlayoffScenarios(data=data, params=params, teams=teams)
bye_scens = ps.get_new_clinches(seed=3)
playoff_scens = ps.get_new_clinches(seed=5)
bootyman_scens = ps.get_new_bootyman_scenarios()
magic_numbers = ps.get_magic_numbers()
standings_df['bye_magic_number'] = standings_df['team'].map(lambda t: magic_numbers.get(t, {}).get('bye', None))
standings_df['playoff_magic_number'] = standings_df['team'].map(lambda t: magic_numbers.get(t, {}).get('playoff', None))
standings_df['bye_status'] = standings_df.apply(
    lambda x: x.wb2_disp if x.wb2_disp in ['c', 'x'] else x.bye_magic_number,
    axis=1
)
standings_df['playoff_status'] = standings_df.apply(
    lambda x: x.wb5_disp if x.wb5_disp in ['c', 'x'] else x.playoff_magic_number,
    axis=1
)

def format_prob(p):
    if 0 < p <= 0.001:
        return "<0.1%"
    elif .999 <= p < 1:
        return ">99.9%"
    else:
        return f"{p*100:.1f}%"

for s in clinches['clinches']:
    if s[1] == 'Bye':
        try:
            prob = format_prob(bye_scens[s[0]]['p_clinch'])
        except KeyError:
            prob = f'0.0%'
        s.extend([prob])
    else:
        try:
            prob = format_prob(playoff_scens[s[0]]['p_clinch'])
        except KeyError:
            prob = f'0.0%'
        s.extend([prob])

for s in clinches['eliminations']:
    if s[1] == 'Bye':
        try:
            prob = format_prob(bye_scens[s[0]]['p_elim'])
        except KeyError:
            prob = f'0.0%'
        s.extend([prob])
    else:
        try:
            prob = format_prob(playoff_scens[s[0]]['p_elim'])
        except KeyError:
            prob = f'0.0%'
        s.extend([prob])
# TODO: fix last week clinches/elims. for wild card, net wins and probability should be blank (or save all sims to get prob of team getting outscored by x pts)

for s in clinches['bootyman']:
    try:
        if s[4] == 'escape':
            prob = format_prob(bootyman_scens[s[0]]['p_escape'])
        else:
            prob = format_prob(bootyman_scens[s[0]]['p_clinch'])
    except KeyError:
        prob = f'0.0%'
    s.extend([prob])

standings_seed_rows = standings_df[['seed', 'team']].to_dict(orient='records')
standings_df = display_team_values(standings_df, ['team'])
clinches['clinches'] = format_scenario_statements(
    clinches['clinches'],
    scenario_type='clinch'
)
clinches['eliminations'] = format_scenario_statements(
    clinches['eliminations'],
    scenario_type='eliminate'
)
clinches['bootyman'] = format_bootyman_scenario_statements(
    clinches['bootyman']
)

all_matchups = teams._fetch_matchups()
previous_week_results = []
previous_week_low_score = None
if previous_week >= 1:
    for matchup in all_matchups:
        if matchup['week'] != previous_week or 'team2' not in matchup:
            continue
        scores = [matchup['score1'], matchup['score2']]
        week_low = min(scores)
        previous_week_low_score = (
            week_low
            if previous_week_low_score is None
            else min(previous_week_low_score, week_low)
        )
        previous_week_results.append([
            team_display_name(matchup['team1']),
            _format_score(matchup['score1']),
            _format_score(matchup['score2']),
            team_display_name(matchup['team2'])
        ])

current_week_matchups = []
for matchup in all_matchups:
    if matchup['week'] != params.current_week or 'team2' not in matchup:
        continue
    current_week_matchups.append({
        'matchup_id': simulations.get_matchup_id(
            teams=teams,
            week=params.current_week,
            team_id=matchup['team1']
        ),
        'team1': team_display_name(matchup['team1']),
        'team2': team_display_name(matchup['team2'])
    })

last_week_bootyman = None
if (
    params.current_week != 1
    and params.current_week <= params.regular_season_end + 1
    and previous_week >= 1
):
    previous_scores = []
    for matchup in all_matchups:
        if matchup['week'] != previous_week:
            continue
        previous_scores.append((matchup['team1'], matchup['score1']))
        if 'team2' in matchup:
            previous_scores.append((matchup['team2'], matchup['score2']))

    if previous_scores:
        bootyman_team_id, bootyman_score = min(
            previous_scores,
            key=lambda item: item[1]
        )
        bootyman_manager = manager_display_name(bootyman_team_id)
        last_week_bootyman = {
            'team': team_display_name(bootyman_team_id),
            'manager': bootyman_manager,
            'score': _format_score(bootyman_score),
            'logo': _logo_path(bootyman_manager)
        }


pr_data = db_pr.retrieve_data(how='season')
pr_cols = ['team', 'total_points', 'weekly_points', 'consistency', 'manager', 'luck', 'power_rank', 'rank_change', 'power_score_norm', 'score_norm_change']
rank_cols = ['team', 'week', 'power_rank', 'power_score_norm']
if pr_data.empty:
    pr_table = pd.DataFrame(columns=pr_cols)
    rank_data = {'rank_data': '[]'}
else:
    pr_data[['power_score_norm', 'score_norm_change']] = round(pr_data[['power_score_norm', 'score_norm_change']] * 100).astype('Int32')
    pr_table = pr_data[pr_data.week == power_data_week]
    pr_table = pr_table.sort_values('power_score_raw', ascending=False)
    pr_table['rank_change'] = -pr_table.rank_change
    pr_table[['total_points', 'weekly_points', 'consistency', 'manager', 'luck']] = pr_table[['season_idx', 'week_idx', 'consistency_idx', 'manager_idx', 'luck_idx']].rank(ascending=False, method='min').astype('Int32')
    pr_table = display_team_values(pr_table, ['team'])
    pr_data = display_team_values(pr_data, ['team'])
    rank_data = pr_data[rank_cols].sort_values(['week', 'power_score_norm'], ascending=[True, False]).to_dict(orient='records')
    rank_data = json.dumps(rank_data, indent=2)
    rank_data = {'rank_data': rank_data}


# SIMULATIONS PAGE
if betting_table.empty:
    timestamp_betting = 'No data'
    betting_table = pd.DataFrame(columns=['matchup_id', 'team', 'avg_score', 'p_win', 'p_tophalf', 'p_highest', 'p_lowest'])
else:
    timestamp_betting = pd.to_datetime(betting_table.created.max()).strftime("%A, %b %d %Y")
    betting_table = betting_table.sort_values(['matchup_id', 'avg_score'])
    betting_table['avg_score'] = betting_table.avg_score.round(2).apply(lambda x: f'{x:.2f}')
    betting_table['p_win'] = betting_table.p_win.apply(lambda x: simulations.calculate_odds(init_prob=x))
    betting_table['p_tophalf'] = betting_table.p_tophalf.apply(lambda x: simulations.calculate_odds(init_prob=x))
    betting_table['p_highest'] = betting_table.p_highest.apply(lambda x: simulations.calculate_odds(init_prob=x))
    betting_table['p_lowest'] = betting_table.p_lowest.apply(lambda x: simulations.calculate_odds(init_prob=x))
    betting_table = display_team_values(betting_table, ['team'])

current_week_matchup_rows = []
for matchup in current_week_matchups:
    matchup_odds = betting_table[
        betting_table.matchup_id == matchup['matchup_id']
    ] if 'matchup_id' in betting_table.columns else pd.DataFrame()
    odds_by_team = dict(zip(matchup_odds.team, matchup_odds.p_win))
    current_week_matchup_rows.append([
        matchup['team1'],
        odds_by_team.get(matchup['team1'], '-'),
        odds_by_team.get(matchup['team2'], '-'),
        matchup['team2']
    ])

is_playoff_week = params.current_week > params.regular_season_end
postseason_home = {
    'show': is_playoff_week,
    'week': params.current_week,
    'bootyman_bowl_logo': 'logos/bootyman_bowl.png',
    'nut_cup_logo': 'logos/quest_for_nut_cup.png',
    'bootyman_matchup': None,
    'this_year_bootyman': None,
    'championship_matchup': None,
    'bracket_games': [],
    'bracket_rounds': []
}

seed_to_manager = {
    int(row['seed']): row['team']
    for row in standings_seed_rows
    if pd.notna(row.get('seed'))
}

bootyman_managers = [
    seed_to_manager[seed]
    for seed in [9, 10]
    if seed in seed_to_manager
]
bootyman_team_ids = [
    teams.primowner_to_teamid[owner_id]
    for owner_id, team_id in teams.primowner_to_teamid.items()
    if constants.TEAM_IDS[owner_id]['name']['display'] in bootyman_managers
]
bootyman_cards = [_team_card_from_manager(manager) for manager in bootyman_managers]
if len(bootyman_cards) == 2:
    postseason_home['bootyman_matchup'] = {
        'teams': bootyman_cards
    }

week_15_bootyman_scores = []
for team_id in bootyman_team_ids:
    for matchup in all_matchups:
        if matchup['week'] != params.regular_season_end + 1:
            continue
        score = _matchup_score(matchup, team_id)
        if score is not None:
            week_15_bootyman_scores.append((team_id, score))
            break

if params.current_week >= params.regular_season_end + 2 and week_15_bootyman_scores:
    bootyman_team_id, _ = min(week_15_bootyman_scores, key=lambda item: item[1])
    postseason_home['this_year_bootyman'] = _team_card_from_team_id(bootyman_team_id)

def _find_matchup_between(week: int, team1_id: int | None, team2_id: int | None) -> dict | None:
    if team1_id is None or team2_id is None:
        return None
    for matchup in all_matchups:
        if matchup['week'] != week or 'team2' not in matchup:
            continue
        matchup_teams = {matchup['team1'], matchup['team2']}
        if {team1_id, team2_id} == matchup_teams:
            return matchup
    return None


def _matchup_winner_id(matchup: dict | None) -> int | None:
    if not matchup:
        return None
    score1 = matchup.get('score1')
    score2 = matchup.get('score2')
    if score1 is None or score2 is None:
        return None
    if score1 == score2:
        return None
    return matchup['team1'] if score1 > score2 else matchup['team2']


def _bracket_game(
    *,
    week: int,
    team1_id: int | None,
    team2_id: int | None,
    team1_label: str = None,
    team2_label: str = None
) -> dict:
    matchup = _find_matchup_between(week, team1_id, team2_id)
    team1_card = _team_card_from_team_id(team1_id) if team1_id else {}
    team2_card = _team_card_from_team_id(team2_id) if team2_id else {}
    team1 = team1_card.get('team', team1_label or 'TBD')
    team2 = team2_card.get('team', team2_label or 'TBD')

    odds_by_team = {}
    if matchup and week == params.current_week and 'matchup_id' in betting_table.columns:
        matchup_id = simulations.get_matchup_id(
            teams=teams,
            week=week,
            team_id=matchup['team1']
        )
        matchup_odds = betting_table[betting_table.matchup_id == matchup_id]
        odds_by_team = dict(zip(matchup_odds.team, matchup_odds.p_win))

    return {
        'week': week,
        'label': f"Week {week}",
        'team1': team1,
        'team2': team2,
        'seed1': team_id_to_seed.get(team1_id, ''),
        'seed2': team_id_to_seed.get(team2_id, ''),
        'logo1': team1_card.get('logo', ''),
        'logo2': team2_card.get('logo', ''),
        'score1': _display_score(_matchup_score(matchup, team1_id)) if week < params.current_week else '',
        'score2': _display_score(_matchup_score(matchup, team2_id)) if week < params.current_week else '',
        'winner': _matchup_winner_id(matchup) if week < params.current_week else None,
        'team1_id': team1_id,
        'team2_id': team2_id,
        'odds1': odds_by_team.get(team1, ''),
        'odds2': odds_by_team.get(team2, '')
    }


seed_team_ids = {
    seed: _team_id_from_manager(manager)
    for seed, manager in seed_to_manager.items()
}
team_id_to_seed = {
    team_id: seed
    for seed, team_id in seed_team_ids.items()
    if team_id is not None
}
play_in_week = params.regular_season_end + 1
semifinal_week = params.regular_season_end + 2
championship_week = params.regular_season_end + 3

play_in_matchup = _find_matchup_between(
    play_in_week,
    seed_team_ids.get(4),
    seed_team_ids.get(5)
)
play_in_winner_id = (
    _matchup_winner_id(play_in_matchup)
    if params.current_week > play_in_week
    else None
)

postseason_home['bracket_games'].append(_bracket_game(
    week=play_in_week,
    team1_id=seed_team_ids.get(4),
    team2_id=seed_team_ids.get(5)
))
postseason_home['bracket_games'].append(_bracket_game(
    week=semifinal_week,
    team1_id=seed_team_ids.get(1),
    team2_id=play_in_winner_id,
    team2_label='Play-In Winner'
))
postseason_home['bracket_games'].append(_bracket_game(
    week=semifinal_week,
    team1_id=seed_team_ids.get(2),
    team2_id=seed_team_ids.get(3)
))

semi_winners = []
if params.current_week > semifinal_week:
    for game in postseason_home['bracket_games']:
        if game['week'] != semifinal_week:
            continue
        team1_id = _team_id_from_display_name(game['team1'])
        team2_id = _team_id_from_display_name(game['team2'])
        semi_winner_id = _matchup_winner_id(
            _find_matchup_between(semifinal_week, team1_id, team2_id)
        )
        if semi_winner_id:
            semi_winners.append(semi_winner_id)

championship_matchup = None
if len(semi_winners) == 2:
    championship_matchup = _bracket_game(
        week=championship_week,
        team1_id=semi_winners[0],
        team2_id=semi_winners[1]
    )
elif params.current_week >= championship_week:
    winner_bracket_matchup_ids = {
        matchup.get('id')
        for matchup in teams.matchups.get('schedule', [])
        if matchup.get('playoffTierType') == 'WINNERS_BRACKET'
    }
    actual_final = next(
        (
            matchup for matchup in all_matchups
            if matchup['week'] == championship_week
            and 'team2' in matchup
            and (
                not winner_bracket_matchup_ids
                or matchup.get('matchup_id') in winner_bracket_matchup_ids
            )
        ),
        None
    )
    if actual_final:
        championship_matchup = _bracket_game(
            week=championship_week,
            team1_id=actual_final['team1'],
            team2_id=actual_final['team2']
        )

postseason_home['bracket_games'].append(
    championship_matchup
    if championship_matchup
    else _bracket_game(
        week=championship_week,
        team1_id=None,
        team2_id=None,
        team1_label='Semifinal Winner',
        team2_label='Semifinal Winner'
    )
)

round_labels = {
    play_in_week: 'Play-In',
    semifinal_week: 'Semifinals',
    championship_week: 'Championship'
}
postseason_home['bracket_rounds'] = [
    {
        'week': bracket_week,
        'label': round_labels.get(bracket_week, f'Week {bracket_week}'),
        'games': [
            game
            for game in postseason_home['bracket_games']
            if game['week'] == bracket_week
        ]
    }
    for bracket_week in range(
        play_in_week,
        championship_week + 1
    )
]
postseason_home['bracket_byes'] = [
    {
        'seed': seed,
        **_team_card_from_team_id(team_id)
    }
    for seed, team_id in seed_team_ids.items()
    if seed in [1, 2, 3] and team_id is not None
]
postseason_home['bracket_rounds'] = [
    bracket_round
    for bracket_round in postseason_home['bracket_rounds']
    if bracket_round['week'] <= params.current_week
    and bracket_round['games']
]

if params.current_week == championship_week:
    current_final = [
        game
        for game in postseason_home['bracket_games']
        if game['week'] == params.current_week
        and game['team1'] != 'Semifinal Winner'
        and game['team2'] != 'Semifinal Winner'
    ]
    if current_final:
        postseason_home['championship_matchup'] = {
            'teams': [
                {
                    'team': current_final[0]['team1'],
                    'logo': current_final[0]['logo1']
                },
                {
                    'team': current_final[0]['team2'],
                    'logo': current_final[0]['logo2']
                }
            ]
        }

keep_cols = ['team', 'projected_wins', 'projected_losses', 'total_points', 'playoffs', 'finals', 'champion']
if season_sim_table.empty:
    timestamp_season_sim = 'No data'
    season_sim_table = pd.DataFrame(columns=keep_cols)
    season_sim_wins_table = pd.DataFrame(columns=['Team'])
    season_sim_ranks_table = pd.DataFrame(columns=['Team'])
else:
    timestamp_season_sim = pd.to_datetime(season_sim_table.created.values[0]).strftime("%A, %b %d %Y")
    season_sim_table[['playoffs', 'finals', 'champion']] = (season_sim_table[['playoffs', 'finals', 'champion']]*100).round(0).astype(int).astype(str) + '%'
    season_sim_table[['matchup_wins', 'tophalf_wins', 'total_wins', 'total_points']] = season_sim_table[['matchup_wins', 'tophalf_wins', 'total_wins', 'total_points']].round(1)
    season_sim_table['projected_wins'] = season_sim_table.matchup_wins.round(1)
    season_sim_table['projected_losses'] = (params.regular_season_end - season_sim_table.matchup_wins).round(1)
    season_sim_table['total_points'] = season_sim_table.total_points.apply(lambda x: f'{x:,.1f}')
    teams_order = [
        record['team']
        for record in league_rules.order_playoff_standings(
            records=[
                {
                    'team': row.team,
                    'wins': row.matchup_wins,
                    'score': float(str(row.total_points).replace(',', ''))
                }
                for _, row in season_sim_table.iterrows()
            ],
            playoff_teams=5
        )
    ]
    season_sim_table = season_sim_table.set_index('team')
    season_sim_table = season_sim_table.reindex(teams_order).reset_index()[keep_cols]

    order = season_sim_table.team.tolist()
    season_sim_table = display_team_values(season_sim_table, ['team'])
    if season_sim_wins_table.empty:
        season_sim_wins_table = pd.DataFrame(columns=['Team'])
    else:
        season_sim_wins_table['p_str'] = round(season_sim_wins_table.p * 100).astype(int)
        season_sim_wins_table = season_sim_wins_table[['team', 'wins', 'p_str']].pivot(index='team', columns='wins', values='p_str').fillna('')
        season_sim_wins_table = season_sim_wins_table.reindex(order).reset_index().rename(columns={'team': 'Team'})
        season_sim_wins_table = display_team_values(season_sim_wins_table, ['Team'])

    if season_sim_ranks_table.empty:
        season_sim_ranks_table = pd.DataFrame(columns=['Team'])
    else:
        season_sim_ranks_table['p_str'] = round(season_sim_ranks_table.p * 100).astype(int)
        season_sim_ranks_table = season_sim_ranks_table[['team', 'ranks', 'p_str']].pivot(index='team', columns='ranks', values='p_str').fillna('')
        season_sim_ranks_table = season_sim_ranks_table.reindex(order).reset_index().rename(columns={'team': 'Team'})
        season_sim_ranks_table = display_team_values(season_sim_ranks_table, ['Team'])


# SCENARIOS PAGE
h2h_data = h2h_data[h2h_data.week <= completed_week] if 'week' in h2h_data.columns else h2h_data
total_wins = scenarios.get_total_wins(h2h_data=h2h_data, teams=teams, week=completed_week + 1)
wins_by_week = scenarios.get_wins_by_week(h2h_data=h2h_data, total_wins=total_wins, teams=teams)
wins_vs_opp = scenarios.get_wins_vs_opp(h2h_data=h2h_data, total_wins=total_wins, wins_by_week=wins_by_week, week=completed_week + 1)
wins_vs_opp = display_team_columns(display_team_values(wins_vs_opp, ['team']))
wins_by_week = display_team_values(wins_by_week, ['team'])

ss_disp_temp = scenarios.get_schedule_switcher_display(ss_data=ss_data, total_wins=total_wins, week=completed_week + 1)
ss_luck_dict = scenarios.calculate_schedule_luck(ss_data)
if ss_luck_dict:
    ss_luck = pd.DataFrame.from_dict(ss_luck_dict, orient='index').reset_index().rename(columns={'index':'team', 0:'Luck'})
else:
    ss_luck = pd.DataFrame({'team': total_wins.team, 'Luck': '+0.0'})
ss_disp = pd.merge(ss_disp_temp, ss_luck, on='team')
ss_disp = display_team_columns(display_team_values(ss_disp, ['team']))


# TEAM EFFICIENCY PAGE
efficiency_display_week = (
    params.regular_season_end
    if params.current_week > params.regular_season_end
    else previous_week
)
efficiency_title = (
    'Final Lineup Efficiency'
    if params.current_week > params.regular_season_end
    else 'Lineup Efficiency'
)
eff_plot = plot_efficiency(
    season=season,
    week=efficiency_display_week,
    x='actual_lineup_score',
    y='optimal_lineup_score',
    xlab='Difference From Optimal Points per Week',
    ylab='Optimal Points per Week',
    title=''
)

# HISTORY/CHAMPIONS PAGE
champs = pd.read_csv(r'champions.csv').sort_values('Season', ascending=False)
prev_champs = champs[['Season', 'Team', 'Runner Up']]

champ_count = (
    pd.concat(
        [
            champs.groupby('Team').size().rename('First'),
            champs.groupby('Runner Up').size().rename('Second')
        ], axis=1
    )
    .fillna(0)
    .sort_values('First', ascending=False)
)

champ_count['First'] = champ_count.First.apply(
    lambda n: ''.join(
        [
            f'<i class="fa fa-trophy icon-gold"></i>{"" if (i + 1) % 3 else "<span><br></span>"}' for i in range(int(n))
        ]
    ) + '<br>'
)
champ_count['Second'] = champ_count.Second.apply(
    lambda n: ''.join(
        [
            f'<i class="fa fa-trophy" style="color: #C0C0C0"></i>{"" if (i + 1) % 3 else "<span><br></span>"}' for i in range(int(n))
        ]
    ) + '<br>'
)
champ_count = champ_count.reset_index().rename(columns={'index': 'Team'})

bootymen = pd.read_csv(r'bootyman_bowl.csv').sort_values('Season', ascending=False)
prev_bootymen = bootymen[['Season', 'Team', 'Runner Up']]

bootyman_teams = pd.Index(
    sorted(set(league_rules.active_team_names()) | set(pd.concat([bootymen['Team'], bootymen['Runner Up']]).dropna()))
)
bootyman_count = (
    pd.concat(
        [
            bootymen.groupby('Team').size().rename('First'),
            bootymen.groupby('Runner Up').size().rename('Second')
        ], axis=1
    )
    .reindex(bootyman_teams)
    .fillna(0)
    .sort_values('First', ascending=False)
)

bootyman_count['First'] = bootyman_count.First.apply(
    lambda n: ''.join(
        [
            f'<i class="fa fa-poop icon-gold"></i>{"" if (i + 1) % 3 else "<span><br></span>"}' for i in range(int(n))
        ]
    ) + '<br>'
)
bootyman_count['Second'] = bootyman_count.Second.apply(
    lambda n: ''.join(
        [
            f'<i class="fa fa-poop icon-silver"></i>{"" if (i + 1) % 3 else "<span><br></span>"}' for i in range(int(n))
        ]
    ) + '<br>'
)
bootyman_count = bootyman_count.reset_index().rename(columns={'index': 'Team'})
