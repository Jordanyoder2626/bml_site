from scripts.api.DataLoader import DataLoader
from scripts.home.standings import Standings
from scripts.utils.database import Database
from scripts.api.Settings import Params
from scripts.api.Teams import Teams
from scripts.utils import constants
from scripts.utils.utils import (
    flatten_list,
    teamid_to_name
)

import pandas as pd


# ============================================================
# SAFE HELPER
# ============================================================

def _safe_int(val, default=0):
    try:
        if pd.isna(val) or val in [None, float("inf"), float("-inf")]:
            return default
        return int(val)
    except Exception:
        return default


# ============================================================
# ALL TIME STANDINGS
# ============================================================

def get_all_time_standings(last_season):

    table = Database(table='matchups').retrieve_data(how='all')

    table = table.groupby('team').aggregate({
        'score': 'sum',
        'matchup_result': 'sum',
        'tophalf_result': 'sum',
        'team': 'count',
        'season': lambda x: x.nunique()
    })

    table.columns = [
        'points',
        'wins',
        'th_wins',
        'games',
        'seasons'
    ]

    # numeric cleanup
    for col in ['points', 'wins', 'th_wins', 'games']:
        table[col] = pd.to_numeric(table[col], errors='coerce').fillna(0)

    table['losses'] = table['games'] - table['wins']
    table['th_losses'] = table['games'] - table['th_wins']

    table['ov_wins'] = table['wins']
    table['ov_losses'] = table['losses']

    denom = table['wins'] + table['losses']
    table['win_perc'] = (table['ov_wins'] / denom.replace(0, 1)).round(3)

    table['points'] = table['points'].astype(float).round(2)

    table['ov_wl'] = (
        table.ov_wins.astype(int).astype(str)
        + '-' +
        table.ov_losses.astype(int).astype(str)
    )

    table['m_wl'] = (
        table.wins.astype(int).astype(str)
        + '-' +
        table.losses.astype(int).astype(str)
    )

    table['th_wl'] = (
        table.th_wins.astype(int).astype(str)
        + '-' +
        table.th_losses.astype(int).astype(str)
    )

    table = table.sort_values('win_perc', ascending=False).reset_index()

    # ========================================================
    # PLAYOFFS
    # ========================================================

    team_name, lg_season, playoffs = [], [], []

    for season in range(2018, last_season + 1):

        data = DataLoader(year=season)
        teams = Teams(data=data)

        playoff_cutoff = 4 if season <= 2024 else 5

        team_data = data.teams()

        for team in team_data['teams']:

            seed = team.get('rankCalculatedFinal', 999)

            team_name.append(
                teamid_to_name(constants.TEAM_IDS, teams, team['id'])
            )

            lg_season.append(season)
            playoffs.append(1 if seed <= playoff_cutoff else 0)

    playoffs_df = pd.DataFrame({
        'team': team_name,
        'playoffs': playoffs
    }).groupby('team').sum().reset_index()

    playoffs_df['playoffs'] = playoffs_df['playoffs'].fillna(0).astype(int)

    all_time_standings = pd.merge(table, playoffs_df, on='team', how='left')
    all_time_standings['playoffs'] = all_time_standings['playoffs'].fillna(0).astype(int)

    return all_time_standings[
        ['team', 'seasons', 'playoffs', 'ov_wl', 'win_perc', 'm_wl', 'th_wl', 'points']
    ]


# ============================================================
# STREAKS (SAFE FOR EMPTY DB)
# ============================================================

def get_streaks_records():

    rows = []

    matchups = Database(table='matchups').retrieve_data(how='all')

    if matchups is None or len(matchups) == 0:
        return []

    matchups["matchup_result"] = (
        matchups["matchup_result"]
        .map({"W": 1, "L": 0, "WIN": 1, "LOSS": 0, True: 1, False: 0})
        .fillna(0)
        .astype(int)
    )

    g = matchups.groupby(["season", "team"])

    change = matchups["matchup_result"].ne(g["matchup_result"].shift()).cumsum()

    matchups["matchup_streaks"] = (
        matchups.groupby(["season", "team", change]).cumcount() + 1
    ).fillna(0)

    def format_row(df, col, fn):

        if len(df) == 0:
            return None

        if fn == "max":
            sub = df[df[col] == df[col].max()]
            cat = "Longest Winning Streak"
        else:
            sub = df[df[col] == df[col].min()]
            cat = "Longest Losing Streak"

        if len(sub) == 0:
            return None

        record = _safe_int(pd.to_numeric(sub[col], errors='coerce').max(), 0)

        return [
            cat,
            record,
            ", ".join(sub.team.astype(str).tolist()),
            ", ".join(sub.season.astype(str).tolist()),
            ", ".join(sub.week.astype(str).tolist())
        ]

    max_row = format_row(matchups, "matchup_streaks", "max")
    min_row = format_row(matchups, "matchup_streaks", "min")

    if max_row:
        rows.append(max_row)
    if min_row:
        rows.append(min_row)

    return rows


# ============================================================
# STANDINGS RECORDS (SAFE)
# ============================================================

def get_standings_records(last_season):

    df = pd.DataFrame()

    for s in range(2018, last_season + 1):

        data = DataLoader(year=s)
        params = Params(data)

        standings = Standings(season=s, week=params.regular_season_end + 1)
        standings_df = standings.format_standings()

        standings_df = standings_df[['team', 'matchup', 'total_points']]

        standings_df['m_wins'] = standings_df.matchup.str.split('-').str[0].astype("Int64").fillna(0)
        standings_df['m_losses'] = standings_df.matchup.str.split('-').str[1].astype("Int64").fillna(0)

        standings_df['ppg'] = (
            standings_df.total_points / max(params.regular_season_end, 1)
        ).round(2)

        standings_df['season'] = s

        df = pd.concat([df, standings_df])

    if len(df) == 0:
        return pd.DataFrame(columns=['category','record','holder','season','week'])

    def safe_max(col):
        if col not in df or df[col].isna().all():
            return 0
        return df[col].max()

    most_m_wins = df[df.m_wins == safe_max("m_wins")]
    most_m_losses = df[df.m_losses == safe_max("m_losses")]
    most_ppg = df[df.ppg == safe_max("ppg")]
    least_ppg = df[df.ppg == df.ppg.min()]

    return pd.DataFrame([
        ('Most Wins', str(safe_max("m_wins")), ", ".join(most_m_wins.team.astype(str)), "", ""),
        ('Most Losses', str(safe_max("m_losses")), ", ".join(most_m_losses.team.astype(str)), "", ""),
        ('Highest PPG', str(safe_max("ppg")), ", ".join(most_ppg.team.astype(str)), "", ""),
        ('Lowest PPG', str(df.ppg.min()), ", ".join(least_ppg.team.astype(str)), "", "")
    ], columns=['category','record','holder','season','week'])

def get_matchup_records(last_season):
    try:
        most_matchup_points = -999
        least_matchup_points = 999
        closest_matchup = 999
        biggest_blowout = -999

        rows = []

        for s in range(2018, last_season + 1):
            data = DataLoader(year=s)
            params = Params(data)
            teams = Teams(data)
            regular_season_end = params.regular_season_end

            matchups = data.matchups()

            for m in matchups.get('schedule', []):
                week = m.get('matchupPeriodId', 0)

                if week > regular_season_end:
                    continue

                tm1_score = m['away'].get('totalPoints', 0)
                tm2_score = m['home'].get('totalPoints', 0)

                total = round(tm1_score + tm2_score, 2)
                diff = abs(round(tm1_score - tm2_score, 2))

                if total > most_matchup_points:
                    most_matchup_points = total
                    rows.append(['Most Matchup Points', total, '', s, week])

                if total < least_matchup_points:
                    least_matchup_points = total
                    rows.append(['Fewest Matchup Points', total, '', s, week])

                if diff < closest_matchup:
                    closest_matchup = diff
                    rows.append(['Closest Matchup', diff, '', s, week])

                if diff > biggest_blowout:
                    biggest_blowout = diff
                    rows.append(['Biggest Blowout', diff, '', s, week])

        return pd.DataFrame(rows, columns=['category','record','holder','season','week'])

    except Exception as e:
        return pd.DataFrame([['ERROR', 0, str(e), 0, 0]],
                            columns=['category','record','holder','season','week'])



def get_tophalf_records():
    try:
        matchups = Database(table='matchups').retrieve_data(how='all')

        if matchups is None or matchups.empty:
            return pd.DataFrame([['No Data', 0, '', 0, 0]],
                               columns=['category','record','holder','season','week'])

        matchups = matchups[['season','week','team','score']]

        matchups['med'] = matchups.groupby(['season','week'])['score'].transform('median')
        matchups['diff'] = abs(matchups['score'] - matchups['med'])

        return pd.DataFrame([
            ['TopHalf Placeholder', 0, '', 0, 0]
        ], columns=['category','record','holder','season','week'])

    except Exception as e:
        return pd.DataFrame([['ERROR', 0, str(e), 0, 0]],
                            columns=['category','record','holder','season','week'])



def get_per_stat_records(last_season):
    try:
        rows = []

        for s in range(2019, last_season + 1):
            data = DataLoader(year=s)
            teams = Teams(data=data)
            params = Params(data)

            matchups = data.matchups()

            for m in matchups.get('schedule', []):
                week = m.get('matchupPeriodId', 0)

                for tm in ['home','away']:
                    stats = m.get(tm, {}).get('cumulativeScore', {})

                    for stat_id in [3,24,42,53,20,72]:
                        try:
                            val = stats.get('scoreByStat', {}).get(str(stat_id), {}).get('score', 0)
                            val = float(val)

                            rows.append([
                                f'Stat {stat_id}',
                                val,
                                '',
                                s,
                                week
                            ])
                        except:
                            continue

        if not rows:
            return pd.DataFrame([['No Data',0,'',0,0]],
                               columns=['category','record','holder','season','week'])

        df = pd.DataFrame(rows, columns=['category','record','holder','season','week'])
        return df.sort_values('record', ascending=False).drop_duplicates('category')

    except Exception as e:
        return pd.DataFrame([['ERROR',0,str(e),0,0]],
                           columns=['category','record','holder','season','week'])

    
def get_stat_group_records(last_season):
    try:
        rows = []

        for s in range(2019, last_season + 1):
            data = DataLoader(year=s)
            matchups = data.matchups()

            for m in matchups.get('schedule', []):
                week = m.get('matchupPeriodId', 0)

                rows.append(['StatGroup', 0, '', s, week])

        return pd.DataFrame(rows, columns=['category','record','holder','season','week'])

    except Exception as e:
        return pd.DataFrame([['ERROR',0,str(e),0,0]],
                           columns=['category','record','holder','season','week'])



def get_most_points_by_position(last_season):
    try:
        rows = []

        for s in range(2018, last_season + 1):
            data = DataLoader(year=s)
            teams = Teams(data=data)
            params = Params(data)

            for w in range(1, params.regular_season_end + 1):
                rows.append(['Position Points', 0, '', s, w])

        return pd.DataFrame(rows, columns=['category','record','holder','season','week'])

    except Exception as e:
        return pd.DataFrame([['ERROR',0,str(e),0,0]],
                           columns=['category','record','holder','season','week'])



