# from scripts.api.DataLoader import DataLoader
# from scripts.api.Settings import Params
# from scripts.utils.database import Database
# from scripts.utils import constants
# from scripts.home.power_ranks import power_rank

# import pandas as pd


# pr_table = 'power_ranks'
# pr_cols = constants.POWER_RANK_COLUMNS
# data = DataLoader(year=constants.SEASON)
# params = Params(data=data)
# # week = params.as_of_week

# for week in range(1, params.current_week):
#     # get previous week data
#     prev_wk = Database(season=constants.SEASON, week=week-1, table='power_ranks').retrieve_data(how='week')

#     df = pd.DataFrame(power_rank(params=params, season=constants.SEASON, week=week)).transpose()
#     df['season'] = constants.SEASON
#     df['week'] = week
#     df = df.reset_index().rename(columns={'index': 'team'})
#     df['id'] = df['season'].astype(str) + '_' + df['week'].astype(str) + '_' + df['team']
#     df['power_rank'] = df.power_score_norm.rank(ascending=False)
#     df_final = pd.concat([prev_wk, df])
#     df_final['score_raw_change'] = df_final.groupby(['team'])['power_score_raw'].diff()
#     df_final['score_norm_change'] = df_final.groupby(['team'])['power_score_norm'].diff()
#     df_final['rank_change'] = df_final.groupby(['team'])['power_rank'].diff()
#     df_final = df_final[pr_cols.split(', ')].fillna(0)
#     df_final = df_final[df_final.week==week]
#     for _, row in df_final.iterrows():
#         pr_vals = tuple(row)
#         db = Database(data=df_final, table=pr_table, columns=pr_cols, values=pr_vals)
#         db.commit_row()
#     print(f'Commited week {week}')


import pandas as pd

from scripts.api.DataLoader import DataLoader
from scripts.api.Settings import Params
from scripts.utils.database import Database
from scripts.home.power_ranks import power_rank
from scripts.utils import constants


PR_TABLE = 'power_ranks'
PR_COLS = constants.POWER_RANK_COLUMNS


def fetch_prev_week(season: int, week: int) -> pd.DataFrame:
    """
    Safely fetch previous week's power rank data.
    Returns empty DF if none exists (prevents Week 1 crash).
    """
    if week <= 1:
        return pd.DataFrame(columns=PR_COLS.split(', '))

    try:
        return Database(
            season=season,
            week=week - 1,
            table=PR_TABLE
        ).retrieve_data(how='week')
    except Exception:
        return pd.DataFrame(columns=PR_COLS.split(', '))


def build_week_df(params, season: int, week: int) -> pd.DataFrame:
    """
    Runs power_rank() and formats output for DB insertion.
    """

    df = pd.DataFrame(
        power_rank(params=params, season=season, week=week)
    ).T

    df['season'] = season
    df['week'] = week

    df = df.reset_index().rename(columns={'index': 'team'})

    # stable ID
    df['id'] = (
        df['season'].astype(str)
        + '_'
        + df['week'].astype(str)
        + '_'
        + df['team'].astype(str)
    )

    # rank calculation (safe + deterministic)
    df['power_rank'] = df['power_score_raw'].rank(ascending=False, method='dense')

    return df


def compute_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes week-over-week changes.
    Requires full concatenated history.
    """

    df = df.sort_values(['team', 'week'])

    df['score_raw_change'] = df.groupby('team')['power_score_raw'].diff()
    df['score_norm_change'] = df.groupby('team')['power_score_norm'].diff() if 'power_score_norm' in df.columns else 0
    df['rank_change'] = df.groupby('team')['power_rank'].diff()

    return df


def write_to_db(df: pd.DataFrame):
    """
    Safe DB insert (row-by-row, controlled schema).
    """

    db = Database(table=PR_TABLE, columns=PR_COLS)

    for _, row in df.iterrows():
        db.values = tuple(row[col] for col in PR_COLS.split(', '))
        db.commit_row()


def main():

    seasons = list(range(2018, 2026))

    for season in seasons:

        data = DataLoader(year=season)
        params = Params(data=data)

        # -----------------------------
        # set max week per season
        # -----------------------------
        if season == 2025:
            max_week = 15
        elif season <= 2020:
            max_week = 13
        else:
            max_week = 14

        for week in range(1, max_week):

            print(f"Processing season {season}, week {week}...")

            # -----------------------------
            # 1. previous week (safe)
            # -----------------------------
            prev_wk = fetch_prev_week(season, week)

            # -----------------------------
            # 2. compute current week
            # -----------------------------
            current_df = build_week_df(params, season, week)

            # -----------------------------
            # 3. combine history
            # -----------------------------
            df_final = pd.concat(
                [prev_wk, current_df],
                ignore_index=True
            )

            # -----------------------------
            # 4. compute deltas safely
            # -----------------------------
            df_final = compute_deltas(df_final)

            # -----------------------------
            # 5. isolate current week
            # -----------------------------
            df_final = df_final[df_final.week == week]

            # -----------------------------
            # 6. enforce schema + clean NaNs
            # -----------------------------
            df_final = df_final.reindex(columns=PR_COLS.split(', ')).fillna(0)

            # -----------------------------
            # 7. prevent duplicate inserts
            # -----------------------------
            try:
                Database(
                    season=season,
                    week=week,
                    table=PR_TABLE
                ).delete(where="week = %s", params=(week,))
            except Exception:
                pass

            # -----------------------------
            # 8. write
            # -----------------------------
            write_to_db(df_final)

            print(f"Committed season {season}, week {week}")


if __name__ == "__main__":
    main()