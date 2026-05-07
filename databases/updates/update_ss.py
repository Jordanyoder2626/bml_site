from scripts.api.DataLoader import DataLoader
from scripts.api.Settings import Params
from scripts.utils.database import Database
from scripts.api.Teams import Teams
from scripts.scenarios.scenarios import schedule_switcher
from scripts.utils import constants

seasons = list(range(2018, 2025))

h2h_table = 'h2h'
h2h_cols = constants.H2H_COLUMNS

for season in seasons:
    data = DataLoader(year=season)
    params = Params(data)
    week = params.as_of_week
    teams = Teams(data)

    for week in range(1, 14):
        switcher = schedule_switcher(teams=teams, season=season, week=week)
        sch_sw_table = 'schedule_switcher'
        sch_sw_cols = constants.SCHEDULE_SWITCH_COLUMNS
        for idx, row in switcher.iterrows():
            ss_vals = (row.id, row.season, row.week, row.team, row.schedule_of, row.result)
            db = Database(data=switcher, table=sch_sw_table, columns=sch_sw_cols, values=ss_vals)
            db.commit_row()
        print(f'Commited week {week}, year {season}')
