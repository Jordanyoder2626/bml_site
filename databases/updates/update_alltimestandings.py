from scripts.records.initialize import *
from scripts.utils.database import Database
from scripts.utils import constants


season=constants.SEASON
standings = get_all_time_standings(season)
standings = standings.reset_index(drop=True).reset_index().rename(columns={'index': 'id'})

records_table = 'alltime_standings'
records_cols = constants.ALLTIME_STANDINGS_COLUMNS
for idx, row in standings.iterrows():
    db = Database(table=records_table, columns=records_cols, values=tuple(row))
    db.sql_insert_query()
    db.commit_row()
