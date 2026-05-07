from scripts.efficiency.efficiencies import get_optimal_points
from scripts.api.DataLoader import DataLoader
from scripts.api.Settings import Params
from scripts.api.Teams import Teams
from scripts.api.Rosters import Rosters
from scripts.utils.database import Database
from scripts.utils import constants


data = DataLoader(year=constants.SEASON)
rosters = Rosters(year=constants.SEASON)
params = Params(data)
week = params.as_of_week
teams = Teams(data=data)
week = 2
week_data = data.load_week(week=week)
eff = get_optimal_points(params=params, teams=teams, rosters=rosters, week_data=week_data, season=constants.SEASON, week=week)
eff_table = 'efficiency'
eff_cols = constants.EFFICIENCY_COLUMNS
for idx, row in eff.iterrows():
    vals = (row.id, row.season, row.week, row.team,
            row.actual_score, row.actual_projected,
            row.best_projected_actual, row.best_projected_proj,
            row.best_lineup_actual, row.best_lineup_proj)
    db = Database(data=eff, table=eff_table, columns=eff_cols, values=vals)
    db.sql_insert_query()
    db.commit_row()
# from scripts.efficiency.efficiencies import get_optimal_points
# from scripts.api.DataLoader import DataLoader
# from scripts.api.Settings import Params
# from scripts.api.Teams import Teams
# from scripts.api.Rosters import Rosters
# from scripts.utils.database import Database
# from scripts.utils import constants


# EFF_TABLE = 'efficiency'
# EFF_COLS = constants.EFFICIENCY_COLUMNS


# def get_weeks_for_season(season: int):
#     if season == 2025:
#         return range(1, 15)
#     return range(1, 14)


# def main():

#     for season in range(2018, 2026):

#         print(f"\nProcessing season {season}...")

#         # load season-level objects ONCE per season
#         data = DataLoader(year=season)
#         rosters = Rosters(year=season)
#         teams = Teams(data=data)
#         params = Params(data)

#         for week in get_weeks_for_season(season):

#             try:
#                 print(f"Processing season {season}, week {week}...")

#                 week_data = data.load_week(week=week)

#                 eff = get_optimal_points(
#                     params=params,
#                     teams=teams,
#                     rosters=rosters,
#                     week_data=week_data,
#                     season=season,
#                     week=week
#                 )

#                 for _, row in eff.iterrows():

#                     vals = (
#                         row.id,
#                         row.season,
#                         row.week,
#                         row.team,
#                         row.actual_score,
#                         row.actual_projected,
#                         row.best_projected_actual,
#                         row.best_projected_proj,
#                         row.best_lineup_actual,
#                         row.best_lineup_proj
#                     )

#                     db = Database(
#                         data=eff,
#                         table=EFF_TABLE,
#                         columns=EFF_COLS,
#                         values=vals
#                     )

#                     db.sql_insert_query()
#                     db.commit_row()

#                 print(f"Finished season {season}, week {week}")

#             except Exception as e:
#                 print(f"ERROR season {season} week {week}: {e}")


# if __name__ == "__main__":
#     main()