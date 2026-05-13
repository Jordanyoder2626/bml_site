from scripts.api.DataLoader import DataLoader
from scripts.simulations.simulations import get_week_projections
from scripts.utils.database import Database
from scripts.utils import constants

import mysql.connector.errors


SEASON = 2025
START_WEEK = 1
END_WEEK = 18

WK_PROJ_TABLE = 'player_projections'
WK_PROJ_COLS = constants.PROJECTIONS_COLUMNS
if isinstance(WK_PROJ_COLS, str):
    WK_PROJ_COLS = [c.strip() for c in WK_PROJ_COLS.split(',')]


def _upsert_query():
    col_str = ", ".join(WK_PROJ_COLS)
    placeholders = ", ".join(["%s"] * len(WK_PROJ_COLS))
    update_str = ", ".join([
        f"{col}=VALUES({col})"
        for col in WK_PROJ_COLS
        if col != "id"
    ])

    return f"""
        INSERT INTO {WK_PROJ_TABLE} ({col_str})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE
        {update_str};
    """


def _projection_rows(week):
    data = get_week_projections(week=week)
    data = data[['id', 'season', 'week', 'player', 'espn_id', 'position', 'rec', 'fpts']]
    data.columns = ['id', 'season', 'week', 'name', 'espn_id', 'position', 'receptions', 'projection']

    return data


def _upsert_projections(cursor, week):
    data = _projection_rows(week=week)
    query = _upsert_query()

    for _, row in data.iterrows():
        values = tuple(row[col] for col in WK_PROJ_COLS)
        cursor.execute(query, values)

    return len(data)


def _update_actuals(cursor, data_loader, week, season=SEASON):
    try:
        players = data_loader.load_week(week=week)['players']
    except Exception as e:
        print(f"  Skipped actuals for week {week}: {e}")
        return

    query = f"""
        UPDATE {WK_PROJ_TABLE}
        SET actual = %s
        WHERE espn_id = %s
          AND season = %s
          AND week = %s;
    """

    for player in players:
        actual = 0

        for stat in player['player'].get('stats', []):
            is_actual = (
                stat.get('seasonId') == season
                and stat.get('scoringPeriodId') == week
                and stat.get('statSourceId') == 0
            )

            if is_actual:
                actual = stat.get('appliedTotal', 0)

        try:
            cursor.execute(query, (actual, player['id'], season, week))
        except mysql.connector.errors.ProgrammingError as e:
            if "Unknown column 'actual'" in str(e):
                print("  Skipped actuals: player_projections.actual does not exist")
                return
            raise


def update_week(season: int, week: int, update_actuals: bool = True) -> int:
    data_loader = DataLoader(year=season)

    with Database() as conn:
        cursor = conn.cursor()
        row_count = _upsert_projections(cursor=cursor, week=week)
        if update_actuals:
            _update_actuals(
                cursor=cursor,
                data_loader=data_loader,
                week=week,
                season=season
            )
        conn.commit()
        return row_count


def main():
    for week in range(START_WEEK, END_WEEK + 1):
        print(f"Processing {SEASON} week {week}")
        row_count = update_week(season=SEASON, week=week)
        print(f"  Upserted {row_count} projections")


if __name__ == '__main__':
    main()
