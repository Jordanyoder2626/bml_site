from scripts.api.DataLoader import DataLoader
from scripts.api.Settings import Params
from scripts.utils.database import Database
from scripts.api.Teams import Teams
from scripts.scenarios.scenarios import get_h2h
from scripts.utils import constants


seasons = list(range(2018, 2026))

h2h_table = 'h2h'
h2h_cols = constants.H2H_COLUMNS

for season in seasons:

    data = DataLoader(year=season)
    params = Params(data)
    teams = Teams(data)

    # -----------------------------
    # set week range per season
    # -----------------------------
    if season == 2025:
        max_week = 15
    else:
        max_week = 14

    for week in range(1, max_week):

        print(f"Processing season {season}, week {week}...")

        h2h = get_h2h(teams=teams, season=season, week=week)

        for idx, row in h2h.iterrows():

            h2h_vals = (
                row.id,
                row.season,
                row.week,
                row.team,
                row.opp,
                row.result
            )

            db = Database(
                data=h2h,
                table=h2h_table,
                columns=h2h_cols,
                values=h2h_vals
            )

            db.commit_row()