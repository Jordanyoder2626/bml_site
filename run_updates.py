import argparse
import time
from collections.abc import Callable

import pandas as pd

from databases.updates import betting_table
from databases.updates import update_power_ranks
from databases.updates import update_season_sims
from databases.updates import update_week_projections
from scripts.api.DataLoader import DataLoader
from scripts.api.Rosters import Rosters
from scripts.api.Settings import Params
from scripts.api.Teams import Teams
from scripts.efficiency.efficiencies import get_optimal_points
from scripts.home.standings import Standings
from scripts.records.initialize import get_all_time_standings
from scripts.records.initialize import get_matchup_records
from scripts.records.initialize import get_standings_records
from scripts.records.initialize import get_streaks_records
from scripts.records.initialize import get_tophalf_records
from scripts.scenarios.scenarios import get_h2h
from scripts.scenarios.scenarios import schedule_switcher
from scripts.simulations import simulations
from scripts.utils import constants
from scripts.utils.database import Database


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Run all BML data updates for the configured season/week.'
    )
    parser.add_argument('--season', type=int, default=constants.SEASON)
    parser.add_argument('--week', type=int, default=constants.CURRENT_WEEK)
    parser.add_argument('--n-sims', type=int, default=1000)
    parser.add_argument(
        '--refresh-betting-projections',
        action='store_true',
        help='Refresh projections again inside the betting table simulation.'
    )
    parser.add_argument(
        '--skip-season-wide',
        action='store_true',
        help='Skip all-time standings and records refreshes.'
    )
    parser.add_argument(
        '--continue-on-error',
        action='store_true',
        help='Run remaining updates even if one update fails.'
    )
    return parser.parse_args()


def _commit_rows(table: str, columns: str, rows: list[tuple]) -> None:
    db = Database(table=table, columns=columns)
    for row in rows:
        db.values = row
        db.commit_row()


def _delete_week(table: str, season: int, week: int) -> None:
    query = f'DELETE FROM {table} WHERE season = %s AND week = %s;'
    with Database() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (season, week))
        conn.commit()
    print(f'  Cleared existing {table} rows for {season} week {week}')


def _delete_all(table: str) -> None:
    query = f'DELETE FROM {table};'
    with Database() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        conn.commit()
    print(f'  Cleared existing {table} rows')


def _update_matchups(season: int, week: int, data: DataLoader, teams: Teams) -> None:
    standings = Standings(season=season, week=week)
    rows = []

    for team_id in teams.team_ids:
        matchup = standings.get_matchup_results(week=week, team_id=team_id)
        if matchup:
            rows.append(tuple(matchup.values()))

    _delete_week(table='matchups', season=season, week=week)
    _commit_rows(
        table='matchups',
        columns=constants.MATCHUP_COLUMNS,
        rows=rows
    )
    print(f'  Committed {len(rows)} matchup rows')


def _update_h2h(season: int, week: int, teams: Teams) -> None:
    h2h = get_h2h(teams=teams, season=season, week=week)
    rows = [
        (
            row.id,
            row.season,
            row.week,
            row.team,
            row.opp,
            row.result
        )
        for _, row in h2h.iterrows()
    ]
    _delete_week(table='h2h', season=season, week=week)
    _commit_rows(table='h2h', columns=constants.H2H_COLUMNS, rows=rows)
    print(f'  Committed {len(rows)} h2h rows')


def _update_schedule_switcher(season: int, week: int, teams: Teams) -> None:
    switcher = schedule_switcher(teams=teams, season=season, week=week)
    rows = [
        (
            row.id,
            row.season,
            row.week,
            row.team,
            row.schedule_of,
            row.result
        )
        for _, row in switcher.iterrows()
    ]
    _delete_week(table='schedule_switcher', season=season, week=week)
    _commit_rows(
        table='schedule_switcher',
        columns=constants.SCHEDULE_SWITCH_COLUMNS,
        rows=rows
    )
    print(f'  Committed {len(rows)} schedule switcher rows')


def _update_efficiencies(
    season: int,
    week: int,
    data: DataLoader,
    params: Params,
    teams: Teams
) -> None:
    rosters = Rosters(year=season)
    week_data = data.load_week(week=week)
    efficiencies = get_optimal_points(
        params=params,
        teams=teams,
        rosters=rosters,
        week_data=week_data,
        season=season,
        week=week
    )
    rows = [
        (
            row.id,
            row.season,
            row.week,
            row.team,
            row.actual_score,
            row.actual_projected,
            row.best_projected_actual,
            row.best_projected_proj,
            row.best_lineup_actual,
            row.best_lineup_proj
        )
        for _, row in efficiencies.iterrows()
    ]
    _delete_week(table='efficiency', season=season, week=week)
    _commit_rows(table='efficiency', columns=constants.EFFICIENCY_COLUMNS, rows=rows)
    print(f'  Committed {len(rows)} efficiency rows')


def _update_power_rank(season: int, week: int, params: Params) -> None:
    previous_week = update_power_ranks.fetch_prev_week(season=season, week=week)
    current_week = update_power_ranks.build_week_df(
        params=params,
        season=season,
        week=week
    )
    power_rank = pd.concat([previous_week, current_week], ignore_index=True)
    power_rank = update_power_ranks.compute_deltas(power_rank)
    power_rank = power_rank[power_rank.week == week]
    power_rank = power_rank.reindex(
        columns=constants.POWER_RANK_COLUMNS.split(', ')
    ).fillna(0)
    _delete_week(table='power_ranks', season=season, week=week)
    update_power_ranks.write_to_db(power_rank)
    print(f'  Committed {len(power_rank)} power rank rows')


def _update_betting_table(
    season: int,
    week: int,
    data: DataLoader,
    params: Params,
    teams: Teams,
    n_sims: int,
    refresh_projections: bool
) -> None:
    rosters = Rosters(year=season)
    _delete_week(table='betting_table', season=season, week=week)
    betting_table.run_week(
        season=season,
        week=week,
        data=data,
        rosters=rosters,
        params=params,
        teams=teams,
        replacement_players=simulations.get_replacement_players(data),
        n_sims=n_sims,
        refresh_projections=refresh_projections
    )


def _update_season_simulations(week: int, season: int) -> None:
    for table in ['season_sim', 'season_sim_wins', 'season_sim_ranks']:
        _delete_week(table=table, season=season, week=week)
    update_season_sims.run_week(week)


def _update_alltime_standings(season: int) -> None:
    standings = get_all_time_standings(season)
    standings = (
        standings
        .reset_index(drop=True)
        .reset_index()
        .rename(columns={'index': 'id'})
    )
    rows = [tuple(row) for _, row in standings.iterrows()]

    _delete_all('alltime_standings')
    _commit_rows(
        table='alltime_standings',
        columns=constants.ALLTIME_STANDINGS_COLUMNS,
        rows=rows
    )
    print(f'  Committed {len(rows)} all-time standings rows')


def _update_records(season: int) -> None:
    records = pd.concat([
        get_standings_records(season),
        pd.DataFrame(
            get_streaks_records(),
            columns=['category', 'record', 'holder', 'season', 'week']
        ),
        get_matchup_records(season),
        get_tophalf_records()
    ], ignore_index=True)
    records = records.fillna('')
    records['season'] = records['season'].astype(str)
    records['week'] = records['week'].astype(str)
    records['holder'] = records['holder'].astype(str).str.slice(0, 100)
    records = records.reset_index(drop=True)
    records.insert(0, 'id', range(1, len(records) + 1))

    columns = [
        column.strip()
        for column in constants.RECORDS_COLUMNS.split(',')
    ]
    records = records[columns]
    rows = [
        tuple(row[column] for column in columns)
        for _, row in records.iterrows()
    ]

    _delete_all('records')
    _commit_rows(table='records', columns=columns, rows=rows)
    print(f'  Committed {len(rows)} records rows')


def _run_step(name: str, fn: Callable[[], None], continue_on_error: bool) -> None:
    print(f'\n== {name} ==')
    start = time.perf_counter()
    try:
        fn()
    except Exception as exc:
        print(f'  ERROR: {exc}')
        if not continue_on_error:
            raise
    else:
        elapsed = time.perf_counter() - start
        print(f'  Finished in {elapsed:.2f}s')


def main() -> None:
    args = _parse_args()
    constants.SEASON = args.season
    constants.CURRENT_WEEK = args.week

    data = DataLoader(year=args.season)
    params = Params(data)
    teams = Teams(data=data)

    steps: list[tuple[str, Callable[[], None]]] = [
        (
            'Week projections',
            lambda: print(
                f"  Upserted {update_week_projections.update_week(args.season, args.week)} projections"
            )
        ),
        (
            'Matchups',
            lambda: _update_matchups(args.season, args.week, data, teams)
        ),
        (
            'H2H',
            lambda: _update_h2h(args.season, args.week, teams)
        ),
        (
            'Schedule switcher',
            lambda: _update_schedule_switcher(args.season, args.week, teams)
        ),
        (
            'Efficiencies',
            lambda: _update_efficiencies(args.season, args.week, data, params, teams)
        ),
        (
            'Power ranks',
            lambda: _update_power_rank(args.season, args.week, params)
        ),
        (
            'Betting table',
            lambda: _update_betting_table(
                season=args.season,
                week=args.week,
                data=data,
                params=params,
                teams=teams,
                n_sims=args.n_sims,
                refresh_projections=args.refresh_betting_projections
            )
        ),
        (
            'Season simulations',
            lambda: _update_season_simulations(args.week, args.season)
        ),
    ]

    if not args.skip_season_wide:
        steps.extend([
            (
                'All-time standings',
                lambda: _update_alltime_standings(args.season)
            ),
            (
                'Records',
                lambda: _update_records(args.season)
            ),
        ])

    print(f'Running updates for season {args.season}, week {args.week}')
    for name, fn in steps:
        _run_step(
            name=name,
            fn=fn,
            continue_on_error=args.continue_on_error
        )

    print('\nAll requested updates finished.')


if __name__ == '__main__':
    main()
