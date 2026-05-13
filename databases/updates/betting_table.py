import argparse
import time
from datetime import datetime as dt

import mysql.connector.errors

from scripts.api.DataLoader import DataLoader
from scripts.api.Settings import Params
from scripts.api.Rosters import Rosters
from scripts.api.Teams import Teams
from scripts.home.standings import Standings
from scripts.utils.database import Database
from scripts.utils import constants
from scripts.simulations import simulations
from databases.updates import update_week_projections


week_sim_table = 'betting_table'
week_sim_cols = constants.WEEK_SIM_COLUMNS
BOOTYMAN_BOWL_MATCHUP_ID = 99


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


def _manager_to_team_id(teams: Teams, manager: str) -> int | None:
    for owner_id, team_id in teams.primowner_to_teamid.items():
        if constants.TEAM_IDS[owner_id]['name']['display'] == manager:
            return team_id
    return None


def _bootyman_bowl_matchup(season: int, week: int, params: Params, teams: Teams) -> dict | None:
    if week != params.regular_season_end + 1:
        return None

    standings = Standings(season=season, week=params.regular_season_end)
    standings.params.as_of_week = params.regular_season_end
    standings_df = standings.format_standings()
    seed_to_manager = dict(zip(standings_df.seed, standings_df.team))

    team1 = _manager_to_team_id(teams=teams, manager=seed_to_manager.get(9))
    team2 = _manager_to_team_id(teams=teams, manager=seed_to_manager.get(10))
    if team1 is None or team2 is None:
        return None

    return {
        'week': week,
        'matchup_id': BOOTYMAN_BOWL_MATCHUP_ID,
        'team1': team1,
        'score1': 0,
        'team2': team2,
        'score2': 0,
        'type': 'POST'
    }


def run_week(
    *,
    season: int,
    week: int,
    data: DataLoader,
    rosters: Rosters,
    params: Params,
    teams: Teams,
    replacement_players: dict,
    n_sims: int,
    refresh_projections: bool = True
) -> None:
    day = dt.now().strftime('%a')
    if refresh_projections:
        print(f'Updating projections for week {week}')
        row_count = update_week_projections.update_week(
            season=season,
            week=week,
            update_actuals=False
        )
        print(f'  Upserted {row_count} projections')

    week_data = data.load_week(week=week)
    matchups = [m for m in teams._fetch_matchups() if m['week'] == week]
    if week > params.regular_season_end:
        matchups = [m for m in matchups if 'team2' in m]
        bootyman_matchup = _bootyman_bowl_matchup(
            season=season,
            week=week,
            params=params,
            teams=teams
        )
        if bootyman_matchup:
            matchup_team_ids_existing = {
                team_id
                for matchup in matchups
                for team_id in [matchup.get('team1'), matchup.get('team2')]
                if team_id is not None
            }
            bootyman_team_ids = {
                bootyman_matchup['team1'],
                bootyman_matchup['team2']
            }
            if not bootyman_team_ids.issubset(matchup_team_ids_existing):
                matchups.append(bootyman_matchup)
    matchup_team_ids = {
        team_id
        for matchup in matchups
        for team_id in [matchup.get('team1'), matchup.get('team2')]
        if team_id is not None
    }
    if not matchup_team_ids:
        print(f'No matchups found for week {week}; skipping.')
        return

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

    for team in matchup_team_ids:
        display_name = constants.TEAM_IDS[teams.teamid_to_primowner[team]]['name']['display']
        if day in ['Thu', 'Sun']:
            db_id = f'{season}_{week:02d}_{display_name}_{day}'
        else:
            db_id = f'{season}_{week:02d}_{display_name}'

        manual_matchups = [
            matchup
            for matchup in matchups
            if matchup.get('matchup_id') == BOOTYMAN_BOWL_MATCHUP_ID
            and team in [matchup.get('team1'), matchup.get('team2')]
        ]
        matchup_id = (
            BOOTYMAN_BOWL_MATCHUP_ID
            if manual_matchups
            else simulations.get_matchup_id(teams=teams, week=week, team_id=team)
        )
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
    parser.add_argument('--include-playoffs', action='store_true')
    parser.add_argument('--regular-season-only', action='store_true')
    parser.add_argument('--skip-projections', action='store_true')
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
        default_end_week = (
            params.regular_season_end
            if args.regular_season_only
            else params.regular_season_end + 3
        )
        end_week = args.end_week or default_end_week
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
            n_sims=args.n_sims,
            refresh_projections=not args.skip_projections
        )


if __name__ == '__main__':
    main()
