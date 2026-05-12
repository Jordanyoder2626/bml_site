from scripts.api.DataLoader import DataLoader
from scripts.api.Settings import Params
from scripts.api.Teams import Teams
from scripts.api.Rosters import Rosters
from scripts.utils.database import Database
from scripts.utils import constants
from scripts.utils import league_rules
from scripts.simulations import simulations

import math
import time
import warnings
import copy

import pandas as pd


warnings.filterwarnings("ignore", category=UserWarning)


N_SIMS = 100
RUN_WEEKS = [week for week in range(1, 15)]


def _set_sim_week(params: Params, week: int) -> Params:
    params.current_week = week
    params.as_of_week = max(week - 1, 0)
    params.weeks_left = (
        0
        if params.as_of_week > params.regular_season_end
        else params.regular_season_end - params.as_of_week
    )
    params.playoff_teams = 5
    return params


def _clean_db_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _upsert_query(table: str, columns: str | list[str]) -> str:
    if isinstance(columns, str):
        columns = [col.strip() for col in columns.split(',')]

    col_str = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_str = ", ".join([
        f"{col}=VALUES({col})"
        for col in columns
        if col != "id"
    ])

    return f"""
        INSERT INTO {table} ({col_str})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE
        {update_str};
    """


def _execute_rows(table: str, columns: str | list[str], rows: list[tuple]) -> None:
    query = _upsert_query(table=table, columns=columns)

    with Database() as conn:
        cursor = conn.cursor()
        for row in rows:
            cursor.execute(query, tuple(_clean_db_value(value) for value in row))
        conn.commit()


def _active_team_names(teams: Teams) -> list[str]:
    active_names = set(league_rules.active_team_names())
    names = []

    for team_id in teams.team_ids:
        team_name = constants.TEAM_IDS[
            teams.teamid_to_primowner[team_id]
        ]['name']['display']

        if team_name in active_names:
            names.append(team_name)

    return names


def _fill_missing_lineup_weeks(lineups: dict, params: Params) -> dict:
    if not lineups:
        return lineups

    available_weeks = sorted(lineups)
    for week in range(params.current_week, params.regular_season_end + 1):
        if week in lineups:
            continue

        fallback_weeks = [w for w in available_weeks if w <= week]
        fallback_week = fallback_weeks[-1] if fallback_weeks else available_weeks[0]
        lineups[week] = copy.deepcopy(lineups[fallback_week])
        available_weeks = sorted(lineups)

    return lineups


def _validate_future_schedule(teams: Teams, params: Params) -> None:
    schedule_weeks = {
        matchup.get('matchupPeriodId')
        for matchup in teams.matchups.get('schedule', [])
    }
    missing_weeks = [
        week
        for week in range(params.current_week, params.regular_season_end + 1)
        if week not in schedule_weeks
    ]
    if missing_weeks:
        raise RuntimeError(
            'Missing future matchup schedule weeks: '
            + ', '.join(str(week) for week in missing_weeks)
        )


def _load_actual_results(params: Params) -> pd.DataFrame:
    if params.as_of_week <= 0:
        return pd.DataFrame(
            columns=['total_points', 'matchup_wins', 'tophalf_wins']
        )

    results = Database(
        table='matchups',
        season=constants.SEASON,
        week=params.as_of_week
    ).retrieve_data(how='season')

    if results.empty:
        return pd.DataFrame(
            columns=['total_points', 'matchup_wins', 'tophalf_wins']
        )

    results = (
        results[['team', 'score', 'matchup_result', 'tophalf_result']]
        .groupby('team')
        .sum()
    )
    results.columns = ['total_points', 'matchup_wins', 'tophalf_wins']
    return results[results.index.isin(league_rules.active_team_names())]


def _load_current_week_sim(params: Params) -> pd.DataFrame:
    if params.current_week > params.regular_season_end:
        return pd.DataFrame(
            columns=['total_points', 'matchup_wins', 'tophalf_wins']
        )

    week_sim = (
        Database(
            table='betting_table',
            season=constants.SEASON,
            week=params.current_week
        )
        .retrieve_data(how='season')
        .sort_values('created')
        .tail(params.league_size)
    )

    if week_sim.empty:
        return pd.DataFrame(
            columns=['total_points', 'matchup_wins', 'tophalf_wins']
        )

    week_sim = week_sim[['team', 'avg_score', 'p_win', 'p_tophalf']].set_index('team')
    week_sim.columns = ['total_points', 'matchup_wins', 'tophalf_wins']
    return week_sim[week_sim.index.isin(league_rules.active_team_names())]


def _playoff_context(data: DataLoader, params: Params, teams: Teams):
    if params.current_week <= params.regular_season_end:
        return None, None, None

    week_data = data.load_week(week=params.current_week)
    week_matchups = [
        matchup
        for matchup in week_data['schedule']
        if matchup['playoffTierType'] == 'WINNERS_BRACKET'
    ]
    playoff_matchup_ids = [
        matchup['id']
        for matchup in week_matchups
        if all(name in matchup.keys() for name in ['home', 'away'])
        and matchup['matchupPeriodId'] == params.current_week
    ]
    playoff_matchups = [
        matchup
        for matchup in teams._fetch_matchups()
        if matchup['matchup_id'] in playoff_matchup_ids
    ]

    projections_df = simulations.get_week_projections(week=params.current_week)
    projections_df.columns = [
        'name',
        'projection',
        'position',
        'receptions',
        'team',
        'season',
        'week',
        'match_on',
        'id',
        'espn_id'
    ]

    return week_data, playoff_matchups, projections_df.to_dict(orient='records')


def _sim_playoff_game(
    team1: str,
    team2: str,
    week: int,
    lineups: dict
) -> str:
    week_lineups = lineups.get(week, {})
    lineup1 = week_lineups.get(team1)
    lineup2 = week_lineups.get(team2)

    if lineup1 is None:
        return team2
    if lineup2 is None:
        return team1

    score1 = simulations.simulate_lineup(lineup1)
    score2 = simulations.simulate_lineup(lineup2)

    while score1 == score2:
        score1 = simulations.simulate_lineup(lineup1)
        score2 = simulations.simulate_lineup(lineup2)

    return team1 if score1 > score2 else team2


def _simulate_bml_playoffs(
    seeded_teams: list[str],
    start_week: int,
    lineups: dict
) -> tuple[list[str], list[str]]:
    """Simulate the BML 5-team playoff bracket.

    Week 15: 4 seed vs 5 seed.
    Week 16: 1 seed vs 4/5 winner, 2 seed vs 3 seed.
    Week 17: championship game.
    """
    if len(seeded_teams) < 2:
        return [], []

    if start_week <= 15 and len(seeded_teams) >= 5:
        play_in_winner = _sim_playoff_game(
            seeded_teams[3],
            seeded_teams[4],
            week=15,
            lineups=lineups
        )
        semifinalists = [
            seeded_teams[0],
            seeded_teams[1],
            seeded_teams[2],
            play_in_winner
        ]
    elif start_week <= 16:
        semifinalists = seeded_teams[:4]
    else:
        finals_teams = seeded_teams[:2]
        champion = [
            _sim_playoff_game(
                finals_teams[0],
                finals_teams[1],
                week=17,
                lineups=lineups
            )
        ]
        return finals_teams, champion

    if len(semifinalists) < 4:
        return [], []

    finals_teams = [
        _sim_playoff_game(
            semifinalists[0],
            semifinalists[3],
            week=16,
            lineups=lineups
        ),
        _sim_playoff_game(
            semifinalists[1],
            semifinalists[2],
            week=16,
            lineups=lineups
        )
    ]
    champion = [
        _sim_playoff_game(
            finals_teams[0],
            finals_teams[1],
            week=17,
            lineups=lineups
        )
    ]

    return finals_teams, champion


def _sim_one_iteration(
    params: Params,
    teams: Teams,
    lineups: dict,
    team_names: list[str],
    to_add: pd.DataFrame,
    replacement_players: dict,
    data: DataLoader,
    rosters: Rosters,
    week_data: dict | None,
    playoff_matchups: list[dict] | None,
    projections_dict: list[dict] | None
) -> dict:
    sim_results = {
        team: {
            'ranks': 0,
            'matchup_wins': 0,
            'tophalf_wins': 0,
            'total_wins': 0,
            'total_points': 0,
            'playoffs': 0,
            'finals': 0,
            'champion': 0
        }
        for team in team_names
    }

    sim_data = simulations.simulate_season(
        params=params,
        teams=teams,
        lineups=lineups,
        team_names=team_names
    )

    if len(to_add) > 0:
        for team, row in to_add.iterrows():
            if team not in sim_data:
                continue

            sim_data[team]['matchup_wins'] += row.matchup_wins
            sim_data[team]['tophalf_wins'] += row.tophalf_wins
            sim_data[team]['total_wins'] += row.matchup_wins
            sim_data[team]['total_points'] += row.total_points

    ordered_records = league_rules.order_playoff_standings(
        records=[
            {
                'team': team,
                'wins': values['total_wins'],
                'score': values['total_points']
            }
            for team, values in sim_data.items()
        ],
        playoff_teams=5
    )

    sim_data_standings = {
        record['team']: sim_data[record['team']]
        for record in ordered_records
    }

    for index, (team, values) in enumerate(sim_data_standings.items()):
        values['ranks'] = index + 1

    if params.current_week <= params.regular_season_end:
        playoff_teams = [
            team
            for team, values in sim_data_standings.items()
            if values['ranks'] <= 5
        ]
    else:
        playoff_teams = []
        for matchup in week_data['schedule']:
            if matchup.get('playoffTierType') != 'WINNERS_BRACKET':
                continue

            team_id = matchup.get('home', {}).get('teamId')
            rank = [
                team for team in teams.teams['teams']
                if team['id'] == team_id
            ][0]['playoffSeed']
            playoff_teams.append({
                'team': constants.TEAM_IDS[
                    teams.teamid_to_primowner[team_id]
                ]['name']['display'],
                'rank': rank
            })

            if 'away' in matchup:
                team_id = matchup['away']['teamId']
                rank = [
                    team for team in teams.teams['teams']
                    if team['id'] == team_id
                ][0]['playoffSeed']
                playoff_teams.append({
                    'team': constants.TEAM_IDS[
                        teams.teamid_to_primowner[team_id]
                    ]['name']['display'],
                    'rank': rank
                })

        playoff_teams = [
            item['team']
            for item in sorted(playoff_teams, key=lambda x: x['rank'])
        ]

    start_week = (
        params.regular_season_end + 1
        if params.current_week <= params.regular_season_end
        else params.current_week
    )
    finals_teams, champion = _simulate_bml_playoffs(
        seeded_teams=playoff_teams,
        start_week=start_week,
        lineups=lineups
    )

    for team in team_names:
        sim_results[team]['ranks'] += sim_data[team]['ranks']
        sim_results[team]['matchup_wins'] += sim_data[team]['matchup_wins']
        sim_results[team]['tophalf_wins'] += sim_data[team]['tophalf_wins']
        sim_results[team]['total_wins'] += sim_data[team]['total_wins']
        sim_results[team]['total_points'] += sim_data[team]['total_points']

        if team in playoff_teams:
            sim_results[team]['playoffs'] += 1
        if team in finals_teams:
            sim_results[team]['finals'] += 1
        if team in champion:
            sim_results[team]['champion'] += 1

    return sim_results


def _build_result_frames(
    all_sim_results: list[dict],
    team_names: list[str],
    params: Params
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    flattened_results = []

    for sim_index, sim_result in enumerate(all_sim_results):
        for team, stats in sim_result.items():
            row = stats.copy()
            row['team'] = team
            row['simulation'] = sim_index
            flattened_results.append(row)

    all_sim_results_df = pd.DataFrame(flattened_results).sort_values('team')
    columns_order = [
        'simulation',
        'team',
        'ranks',
        'matchup_wins',
        'tophalf_wins',
        'total_wins',
        'total_points',
        'playoffs',
        'finals',
        'champion'
    ]
    all_sim_results_df = all_sim_results_df[columns_order].fillna(0)

    wins_rows = []
    for team in team_names:
        temp = all_sim_results_df[all_sim_results_df.team == team]

        for wins in range(0, params.regular_season_end + 1):
            prob = len(temp[temp.total_wins == wins]) / N_SIMS
            wins_rows.append([team, wins, prob])

    wins_prob_df = pd.DataFrame(wins_rows, columns=['team', 'wins', 'p'])
    wins_prob_df['season'] = constants.SEASON
    wins_prob_df['week'] = params.current_week
    wins_prob_df['id'] = (
        wins_prob_df.season.astype(str)
        + '_'
        + wins_prob_df.week.astype(str).str.zfill(2)
        + '_'
        + wins_prob_df.wins.astype(str).str.zfill(2)
        + '_'
        + wins_prob_df.team
    )

    ranks_prob_df = (
        all_sim_results_df
        .groupby(['team', 'ranks'])
        .simulation
        .count()
        .reset_index()
        .rename(columns={'simulation': 'p'})
    )
    ranks_prob_df['p'] = ranks_prob_df.p / N_SIMS
    rank_index = pd.MultiIndex.from_product(
        [team_names, range(1, len(team_names) + 1)],
        names=['team', 'ranks']
    )
    ranks_prob_df = (
        ranks_prob_df
        .set_index(['team', 'ranks'])
        .reindex(rank_index, fill_value=0)
        .reset_index()
    )
    ranks_prob_df['season'] = constants.SEASON
    ranks_prob_df['week'] = params.current_week
    ranks_prob_df['id'] = (
        ranks_prob_df.season.astype(str)
        + '_'
        + ranks_prob_df.week.astype(str).str.zfill(2)
        + '_'
        + ranks_prob_df.ranks.astype(str).str.zfill(2)
        + '_'
        + ranks_prob_df.team
    )

    team_totals = {
        team: {
            'matchup_wins': 0,
            'tophalf_wins': 0,
            'total_wins': 0,
            'total_points': 0,
            'playoffs': 0,
            'finals': 0,
            'champion': 0
        }
        for team in team_names
    }

    for team in team_names:
        for sim_result in all_sim_results:
            team_totals[team]['matchup_wins'] += sim_result[team]['matchup_wins']
            team_totals[team]['tophalf_wins'] += sim_result[team]['tophalf_wins']
            team_totals[team]['total_wins'] += sim_result[team]['total_wins']
            team_totals[team]['total_points'] += sim_result[team]['total_points']
            team_totals[team]['playoffs'] += sim_result[team]['playoffs']
            team_totals[team]['finals'] += sim_result[team]['finals']
            team_totals[team]['champion'] += sim_result[team]['champion']

    sim_df = pd.DataFrame(team_totals).transpose() / N_SIMS
    sim_df = sim_df.fillna(0).reset_index().rename(columns={'index': 'team'})
    sim_df[['playoffs', 'finals', 'champion']] = (
        sim_df[['playoffs', 'finals', 'champion']]
        .clip(lower=0, upper=0.9999)
    )
    sim_df['season'] = constants.SEASON
    sim_df['week'] = params.current_week
    sim_df['id'] = (
        sim_df.season.astype(str)
        + '_'
        + sim_df.week.astype(str).str.zfill(2)
        + '_'
        + sim_df.team
    )

    return sim_df, wins_prob_df, ranks_prob_df


def _write_results(
    sim_df: pd.DataFrame,
    wins_prob_df: pd.DataFrame,
    ranks_prob_df: pd.DataFrame
) -> None:
    season_sim_rows = [
        (
            row.id,
            row.season,
            row.week,
            row.team,
            row.matchup_wins,
            row.tophalf_wins,
            row.total_wins,
            row.total_points,
            row.playoffs,
            row.finals,
            row.champion
        )
        for _, row in sim_df.iterrows()
    ]
    _execute_rows(
        table='season_sim',
        columns=constants.SEASON_SIM_COLUMNS,
        rows=season_sim_rows
    )

    wins_rows = [
        (row.id, row.season, row.week, row.team, row.wins, row.p)
        for _, row in wins_prob_df.iterrows()
    ]
    _execute_rows(
        table='season_sim_wins',
        columns='id, season, week, team, wins, p',
        rows=wins_rows
    )

    ranks_rows = [
        (row.id, row.season, row.week, row.team, row.ranks, row.p)
        for _, row in ranks_prob_df.iterrows()
    ]
    _execute_rows(
        table='season_sim_ranks',
        columns='id, season, week, team, ranks, p',
        rows=ranks_rows
    )


def run_week(sim_week: int) -> None:
    print(f"Processing season sim week {sim_week}")
    start = time.perf_counter()

    data = DataLoader(year=constants.SEASON)
    params = _set_sim_week(Params(data), sim_week)
    teams = Teams(data)
    _validate_future_schedule(teams=teams, params=params)
    rosters = Rosters()
    replacement_players = simulations.get_replacement_players(data)
    lineups = simulations.get_ros_projections(
        data=data,
        params=params,
        teams=teams,
        rosters=rosters,
        replacement_players=replacement_players
    )
    lineups = _fill_missing_lineup_weeks(lineups=lineups, params=params)
    team_names = _active_team_names(teams)

    results = _load_actual_results(params=params)
    to_add = results

    week_data, playoff_matchups, projections_dict = _playoff_context(
        data=data,
        params=params,
        teams=teams
    )

    all_sim_results = [
        _sim_one_iteration(
            params=params,
            teams=teams,
            lineups=lineups,
            team_names=team_names,
            to_add=to_add,
            replacement_players=replacement_players,
            data=data,
            rosters=rosters,
            week_data=week_data,
            playoff_matchups=playoff_matchups,
            projections_dict=projections_dict
        )
        for _ in range(N_SIMS)
    ]

    sim_df, wins_prob_df, ranks_prob_df = _build_result_frames(
        all_sim_results=all_sim_results,
        team_names=team_names,
        params=params
    )
    _write_results(
        sim_df=sim_df,
        wins_prob_df=wins_prob_df,
        ranks_prob_df=ranks_prob_df
    )

    end = time.perf_counter()
    print(f"  Finished week {sim_week} in {end - start:.2f} seconds")


def main() -> None:
    for week in RUN_WEEKS:
        run_week(week)


if __name__ == '__main__':
    main()
