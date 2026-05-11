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


def _get_matchups_db():
    matchups = Database(table='matchups').retrieve_data(how='all')

    if matchups is None or len(matchups) == 0:
        return pd.DataFrame()

    matchups = matchups.copy()

    for col in ['season', 'week', 'score', 'opponent_score', 'matchup_result', 'tophalf_result']:
        if col in matchups:
            matchups[col] = pd.to_numeric(matchups[col], errors='coerce')

    matchups = matchups.dropna(subset=['season', 'week', 'team', 'score'])
    matchups['season'] = matchups['season'].astype(int)
    matchups['week'] = matchups['week'].astype(int)

    return matchups.sort_values(['season', 'team', 'week']).reset_index(drop=True)


def _join_values(series):
    return ", ".join(series.dropna().astype(str).drop_duplicates().tolist())


def _format_record(value):
    if pd.isna(value):
        return ''

    value = float(value)
    return str(int(value)) if value.is_integer() else f'{value:.2f}'


def _record_rows(df, category, record_col, holder_col='team'):
    return [
        category,
        _format_record(df[record_col].iloc[0]),
        _join_values(df[holder_col]),
        _join_values(df['season']),
        _join_values(df['week'])
    ]


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

    matchups = _get_matchups_db()

    if matchups is None or len(matchups) == 0:
        return []

    matchups = matchups.dropna(subset=['matchup_result']).copy()
    matchups["matchup_result"] = matchups["matchup_result"].astype(int)

    g = matchups.groupby(["season", "team"])
    matchups["new_streak"] = matchups["matchup_result"].ne(g["matchup_result"].shift())
    matchups["streak_group"] = matchups.groupby(["season", "team"])["new_streak"].cumsum()
    matchups["matchup_streak"] = (
        matchups
        .groupby(["season", "team", "streak_group"])
        .cumcount() + 1
    )

    streaks = (
        matchups
        .groupby(["season", "team", "streak_group", "matchup_result"], as_index=False)
        .agg(
            record=("matchup_streak", "max"),
            start_week=("week", "min"),
            end_week=("week", "max")
        )
    )
    streaks["week_range"] = (
        streaks["start_week"].astype(int).astype(str)
        + "-"
        + streaks["end_week"].astype(int).astype(str)
    )

    def format_row(df, result, cat):

        sub = df[df["matchup_result"] == result]
        if len(sub) == 0:
            return None

        sub = sub[sub["record"] == sub["record"].max()]
        if len(sub) == 0:
            return None

        record = _safe_int(pd.to_numeric(sub["record"], errors='coerce').max(), 0)

        return [
            cat,
            record,
            _join_values(sub.team),
            _join_values(sub.season),
            _join_values(sub.week_range)
        ]

    max_row = format_row(streaks, 1, "Longest Winning Streak")
    min_row = format_row(streaks, 0, "Longest Losing Streak")

    if max_row:
        rows.append(max_row)
    if min_row:
        rows.append(min_row)

    return rows


# ============================================================
# STANDINGS RECORDS (SAFE)
# ============================================================

def get_standings_records(last_season):

    matchups = _get_matchups_db()

    if matchups is None or len(matchups) == 0:
        return pd.DataFrame(columns=['category','record','holder','season','week'])

    matchups = matchups[matchups.season <= last_season].copy()
    matchups = matchups.dropna(subset=['matchup_result'])

    df = (
        matchups
        .groupby(['season', 'team'], as_index=False)
        .agg(
            m_wins=('matchup_result', 'sum'),
            games=('matchup_result', 'count'),
            total_points=('score', 'sum'),
            week=('week', 'max')
        )
    )
    df['m_losses'] = df['games'] - df['m_wins']
    df['ppg'] = (df['total_points'] / df['games'].replace(0, 1)).round(2)

    if len(df) == 0:
        return pd.DataFrame(columns=['category','record','holder','season','week'])

    most_m_wins = df[df.m_wins == df.m_wins.max()]
    most_m_losses = df[df.m_losses == df.m_losses.max()]
    most_ppg = df[df.ppg == df.ppg.max()]
    least_ppg = df[df.ppg == df.ppg.min()]

    return pd.DataFrame([
        _record_rows(most_m_wins, 'Most Wins', 'm_wins'),
        _record_rows(most_m_losses, 'Most Losses', 'm_losses'),
        _record_rows(most_ppg, 'Highest PPG', 'ppg'),
        _record_rows(least_ppg, 'Lowest PPG', 'ppg')
    ], columns=['category','record','holder','season','week'])

def get_matchup_records(last_season):
    try:
        matchups = _get_matchups_db()

        if matchups is None or matchups.empty:
            return pd.DataFrame(columns=['category','record','holder','season','week'])

        matchups = matchups[
            (matchups.season <= last_season)
            & matchups.opponent.notna()
            & matchups.opponent_score.notna()
        ].copy()

        if matchups.empty:
            return pd.DataFrame(columns=['category','record','holder','season','week'])

        matchups['pair_key'] = matchups.apply(
            lambda x: "|".join(sorted([str(x.team), str(x.opponent)])),
            axis=1
        )
        matchups = matchups.drop_duplicates(['season', 'week', 'pair_key'])
        matchups['total_points'] = (matchups.score + matchups.opponent_score).round(2)
        matchups['margin'] = (matchups.score - matchups.opponent_score).abs().round(2)
        matchups['holder'] = matchups.apply(
            lambda x: f'{x.team} vs {x.opponent}',
            axis=1
        )

        def category_row(category, col, highest=True):
            target = matchups[col].max() if highest else matchups[col].min()
            sub = matchups[matchups[col] == target]

            if category == 'Biggest Blowout':
                sub = sub.copy()
                sub['holder'] = sub.apply(
                    lambda x: (
                        f'{x.team} over {x.opponent}'
                        if x.score >= x.opponent_score
                        else f'{x.opponent} over {x.team}'
                    ),
                    axis=1
                )

            return _record_rows(sub, category, col, holder_col='holder')

        rows = [
            category_row('Most Matchup Points', 'total_points', highest=True),
            category_row('Fewest Matchup Points', 'total_points', highest=False),
            category_row('Closest Matchup', 'margin', highest=False),
            category_row('Biggest Blowout', 'margin', highest=True)
        ]
        return pd.DataFrame(rows, columns=['category','record','holder','season','week'])

    except Exception as e:
        return pd.DataFrame([['ERROR', 0, str(e), 0, 0]],
                            columns=['category','record','holder','season','week'])



def get_tophalf_records():
    try:
        matchups = _get_matchups_db()

        if matchups is None or matchups.empty:
            return pd.DataFrame(columns=['category','record','holder','season','week'])

        matchups = matchups[['season','week','team','score']].copy()

        matchups['med'] = matchups.groupby(['season','week'])['score'].transform('median')
        matchups['tophalf_win'] = (matchups['score'] > matchups['med']).astype(int)

        records = (
            matchups
            .groupby(['season', 'team'], as_index=False)
            .agg(
                th_wins=('tophalf_win', 'sum'),
                games=('tophalf_win', 'count'),
                week=('week', 'max')
            )
        )
        records['th_losses'] = records['games'] - records['th_wins']

        most_wins = records[records.th_wins == records.th_wins.max()]
        most_losses = records[records.th_losses == records.th_losses.max()]

        return pd.DataFrame([
            _record_rows(most_wins, 'Most Top Half Wins', 'th_wins'),
            _record_rows(most_losses, 'Most Top Half Losses', 'th_losses')
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



