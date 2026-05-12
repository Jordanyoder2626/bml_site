import argparse
import time
from datetime import datetime as dt

import mysql.connector.errors

from scripts.api.DataLoader import DataLoader
from scripts.api.Settings import Params
from scripts.api.Rosters import Rosters
from scripts.api.Teams import Teams
from scripts.utils.database import Database
from scripts.utils import constants
from scripts.simulations import simulations


week_sim_table = 'betting_table'
week_sim_cols = constants.WEEK_SIM_COLUMNS


def _db_probability(value: float) -> float:
    """Fit probabilities into the current DECIMAL(4,4) betting_table columns."""
    return min(max(value, 0), 0.9999)


def _load_projections(season: int, week: int) -> list[dict]:
    projections_df = simulations.query_projections_db(season=season, week=week)
    if projections_df.empty:
        projections_df = simulations.get_week_projections(week=week)
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
    return projections_df.to_dict(orient='records')


def run_week(
    *,
    season: int,
    week: int,
    data: DataLoader,
    rosters: Rosters,
    params: Params,
    teams: Teams,
    replacement_players: dict,
    n_sims: int
) -> None:
    day = dt.now().strftime('%a')
    week_data = data.load_week(week=week)
    matchups = [m for m in teams._fetch_matchups() if m['week'] == week]
    projections = _load_projections(season=season, week=week)

    start = time.perf_counter()
    sim_scores, sim_wins, sim_tophalf, sim_highest, sim_lowest = simulations.simulate_week(
        week_data=week_data,
        teams=teams,
        rosters=rosters,
        params=params,
        replacement_players=replacement_players,
        matchups=matchups,
        projections=projections,
        week=week,
        n_sims=n_sims,
        use_actuals=False
    )
    end = time.perf_counter()

    for team in teams.team_ids:
        display_name = constants.TEAM_IDS[teams.teamid_to_primowner[team]]['name']['display']
        if day in ['Thu', 'Sun']:
            db_id = f'{season}_{week:02d}_{display_name}_{day}'
        else:
            db_id = f'{season}_{week:02d}_{display_name}'

        matchup_id = simulations.get_matchup_id(teams=teams, week=week, team_id=team)
        avg_score = sim_scores[team] / n_sims
        p_win = _db_probability(sim_wins[team] / n_sims)
        p_tophalf = _db_probability(sim_tophalf[team] / n_sims)
        p_highest = _db_probability(sim_highest[team] / n_sims)
        p_lowest = _db_probability(sim_lowest[team] / n_sims)
        week_sim_vals = (
            db_id,
            season,
            week,
            matchup_id,
            display_name,
            avg_score,
            p_win,
            p_tophalf,
            p_highest,
            p_lowest
        )
        print(week_sim_vals)
        try:
            db = Database(table=week_sim_table, columns=week_sim_cols, values=week_sim_vals)
            db.commit_row()
        except mysql.connector.errors.IntegrityError:
            db = Database(table=week_sim_table)
            db.sql_update_table(set_column='avg_score', new_value=avg_score, id_column='id', id_value=db_id, season=season, week=week)
            db.sql_update_table(set_column='p_win', new_value=p_win, id_column='id', id_value=db_id, season=season, week=week)
            db.sql_update_table(set_column='p_tophalf', new_value=p_tophalf, id_column='id', id_value=db_id, season=season, week=week)
            db.sql_update_table(set_column='p_highest', new_value=p_highest, id_column='id', id_value=db_id, season=season, week=week)
            db.sql_update_table(set_column='p_lowest', new_value=p_lowest, id_column='id', id_value=db_id, season=season, week=week)

    print(f'Committed week {week} in {round((end - start) / 60, 2)} minutes')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate betting table simulations.')
    parser.add_argument('--season', type=int, default=constants.SEASON)
    parser.add_argument('--week', type=int)
    parser.add_argument('--start-week', type=int)
    parser.add_argument('--end-week', type=int)
    parser.add_argument('--all-weeks', action='store_true')
    parser.add_argument('--n-sims', type=int, default=1000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data = DataLoader(year=args.season)
    rosters = Rosters(year=args.season)
    params = Params(data)
    teams = Teams(data=data)
    replacement_players = simulations.get_replacement_players(data)

    if args.all_weeks:
        start_week = args.start_week or 1
        end_week = args.end_week or params.regular_season_end
        weeks = range(start_week, end_week + 1)
    elif args.start_week or args.end_week:
        start_week = args.start_week or args.week or params.current_week
        end_week = args.end_week or start_week
        weeks = range(start_week, end_week + 1)
    else:
        weeks = [args.week or params.current_week]

    for week in weeks:
        run_week(
            season=args.season,
            week=week,
            data=data,
            rosters=rosters,
            params=params,
            teams=teams,
            replacement_players=replacement_players,
            n_sims=args.n_sims
        )


if __name__ == '__main__':
    main()
