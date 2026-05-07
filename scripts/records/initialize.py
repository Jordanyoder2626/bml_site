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


def get_all_time_standings(last_season):
    """
    Calculate all-time standings dating back to the 2014 season
    Includes total seasons played and number of times making the playoffs
    """
    table = Database(table='matchups').retrieve_data(how='all')
    table = table.groupby('team').aggregate({
        'score':'sum',
        'matchup_result':'sum',
        'tophalf_result':'sum',
        'team':'count',
        'season':lambda x: x.nunique()
    })
    # table.columns = ['points', 'wins', 'th_wins', 'games', 'seasons']
    # table['losses'] = pd.to_numeric(table.games - table.wins, errors='coerce')
    # table['th_losses'] = pd.to_numeric(table.games - table.th_wins, errors='coerce')
    # table['ov_wins'] = pd.to_numeric(table.wins + table.th_wins, errors='coerce')
    # table['ov_losses'] = pd.to_numeric(table.losses + table.th_losses, errors='coerce')
    # table['win_perc'] = round(table['ov_wins'] / (table['ov_wins'] + table['ov_losses']), 3).map('{:.3f}'.format)
    # table['points'] = round(table.points, 2).map('{:,.2f}'.format)
    table.columns = ['points', 'wins', 'th_wins', 'games', 'seasons']
    print(table.head())
    print(table.dtypes)
    print(table.isna().sum())
    # convert to numeric FIRST
    for col in ['points', 'wins', 'th_wins', 'games']:
        table[col] = pd.to_numeric(table[col], errors='coerce')
    print(table.head())
    print(table.dtypes)
    print(table.isna().sum())
    # derived stats
    table['losses'] = table['games'] - table['wins']
    print(table.head())
    print(table.dtypes)
    print(table.isna().sum())
    table['th_losses'] = table['games'] - table['th_wins']

    table['ov_wins'] = table['wins'] + table['th_wins']
    table['ov_losses'] = table['losses'] + table['th_losses']

    # win percentage
    denom = table['ov_wins'] + table['ov_losses']
    table['win_perc'] = (table['ov_wins'] / denom).round(3)

    # formatted points
    table['points'] = table['points'].astype(float).round(2)
    
    table['ov_wl'] = table.ov_wins.astype(int).astype(str) + '-' + table.ov_losses.astype(int).astype(str)
    table['m_wl'] = table.wins.astype(int).astype(str) + '-' + table.losses.astype(int).astype(str)
    table['th_wl'] = table.th_wins.astype(int).astype(str) + '-' + table.th_losses.astype(int).astype(str)
    table = table.sort_values('win_perc', ascending=False)
    table = table.reset_index()[['team', 'seasons', 'ov_wl', 'win_perc', 'm_wl', 'th_wl', 'points']]

    team_name = []
    lg_season = []
    playoffs = []
    for season in range(2018, last_season):
        print(season)
        # get playoff appearances
        data = DataLoader(year=season)
        params = Params(data=data)
        teams = Teams(data=data)
        team_data = data.teams()
        for team in team_data['teams']:
            playoff_seed = team['rankCalculatedFinal']
            num_teams = params.playoff_teams
            if playoff_seed <= num_teams:
                playoffs.append(1 if playoff_seed <= num_teams else 0)
                lg_season.append(season)
                team_name.append(teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=team['id']))
    playoffs_df = pd.DataFrame(
        {'season': lg_season,
         'team': team_name,
         'playoffs': playoffs
         })
    playoffs_df = playoffs_df[['team', 'playoffs']].groupby('team').sum('playoffs').reset_index()
    #playoffs_2014 = pd.read_csv(r'tables/playoffs_2014_2017.csv')[['team', 'playoffs']]
    playoffs_df_new = playoffs_df
    playoffs_df_new = playoffs_df_new.groupby('team').sum('playoffs').reset_index()
    #all_time_standings = pd.merge(table, playoffs_df_new, on='team').iloc[:, [0, 1, 7, 2, 3, 4, 5, 6]]
    table.to_csv("output.csv", index=False)
    all_time_standings = table.iloc[:, [0, 1, 7, 2, 3, 4, 5, 6]]

    return all_time_standings


def get_streaks_records():
    """
    Calculate longest winning and losing streak for the following:
    - Head to head
    - Top half win (consecutive weeks above league median)
    - Overall (consecutive weeks with h2h AND top half wins)
    Positive values indicate a winning streak, negative values indicate a losing streak
    """
    rows = []
    def format_row(matchups_df: pd.DataFrame, col: str, fn: str) -> list[str]:
        if fn == 'max':
            df = matchups_df[matchups_df[col] == matchups_df[col].max()]
        elif fn == 'min':
            df = matchups_df[matchups_df[col] == matchups_df[col].min()]
        else:
            raise ValueError("fn must either be max or min")

        if col == 'matchup_streaks' and fn == 'max':
            cat = 'Longest Matchup Winning Streak'
        if col == 'tophalf_streaks' and fn == 'max':
            cat = 'Longest Top Half Winning Streak'
        if col == 'overall_streaks' and fn == 'max':
            cat = 'Longest Unbeaten Streak'
        if col == 'matchup_streaks' and fn == 'min':
            cat = 'Longest Matchup Losing Streak'
        if col == 'tophalf_streaks' and fn == 'min':
            cat = 'Longest Top Half Losing Streak'
        if col == 'overall_streaks' and fn == 'min':
            cat = 'Longest Winless Streak'

        record = abs(int(pd.to_numeric(df[col], errors='coerce').max()))
        holder = ', '.join(df.team.tolist())
        season = ', '.join([str(x) for x in df.season.tolist()])
        weeks = ', '.join([f'{x-record+1}-{x}' for x in df.week.tolist()])
        return [cat, record, holder, season, weeks]

    matchups = Database(table='matchups').retrieve_data(how='all')
    matchups = matchups.replace(0, -1)
    matchups['overall_result'] = matchups.matchup_result + matchups.tophalf_result

    result_map = {
        "W": 1, "L": 0,
        "WIN": 1, "LOSS": 0,
        True: 1, False: 0
    }

    matchups["matchup_result"] = matchups["matchup_result"].map(result_map).astype(int)
    matchups["tophalf_result"] = matchups["tophalf_result"].map(result_map).astype(int)
    matchups["overall_result"] = matchups["overall_result"].map(result_map).astype(int)

    g = matchups.groupby(["season", "team"])

    change = matchups["matchup_result"].ne(g["matchup_result"].shift()).cumsum()

    matchups["matchup_streaks"] = (
        matchups.groupby(["season", "team", change]).cumcount() + 1
    )


    g = matchups.groupby(["season", "team"])

    change = matchups["tophalf_result"].ne(g["tophalf_result"].shift()).cumsum()

    matchups["tophalf_streaks"] = (
        matchups.groupby(["season", "team", change]).cumcount() + 1
    )


    g = matchups.groupby(["season", "team"])

    change = matchups["overall_result"].ne(g["overall_result"].shift()).cumsum()

    matchups["overall_streaks"] = (
        matchups.groupby(["season", "team", change]).cumcount() + 1
    )

    # ## head-to-head streaks
    # mws = matchups.matchup_result.groupby([matchups.season, matchups.team]).transform(lambda x: x.diff().ne(0).cumsum())
    # matchups['matchup_streaks'] = matchups.matchup_result.groupby([matchups.season, matchups.team, mws]).cumsum()

    # ## top half streaks
    # thws = matchups.tophalf_result.groupby([matchups.season, matchups.team]).transform(lambda x: x.diff().ne(0).cumsum())
    # matchups['tophalf_streaks'] = matchups.tophalf_result.groupby([matchups.season, matchups.team, thws]).cumsum()

    # ## overall streaks
    # ows = matchups.overall_result.groupby([matchups.season, matchups.team]).transform(lambda x: x.diff().ne(0).cumsum())
    # matchups['overall_streaks'] = matchups.overall_result.groupby([matchups.season, matchups.team, ows]).cumsum() / 2

    rows.append(format_row(matchups, 'matchup_streaks', fn='max'))
    rows.append(format_row(matchups, 'matchup_streaks', fn='min'))
    rows.append(format_row(matchups, 'tophalf_streaks', fn='max'))
    rows.append(format_row(matchups, 'tophalf_streaks', fn='min'))
    rows.append(format_row(matchups, 'overall_streaks', fn='max'))
    rows.append(format_row(matchups, 'overall_streaks', fn='min'))
    return rows


def get_standings_records(last_season):
    """
    Calculate standings-related records:
    - Most matchup and top half wins and losses
    - Highest/lowest PPG
    """
    df = pd.DataFrame()
    for s in range(2018, last_season + 1):
        print(s)
        data = DataLoader(year=s)
        params = Params(data)
        regular_season_end = params.regular_season_end
        standings = Standings(season=s, week=regular_season_end+1)
        standings_df = standings.format_standings()
        standings_df = standings_df[['team', 'matchup', 'top_half', 'total_points']]
        standings_df['m_wins'] = standings_df.matchup.str.split('-').str[0].astype('Int32')
        standings_df['m_losses'] = standings_df.matchup.str.split('-').str[1].astype('Int32')
        standings_df['th_wins'] = standings_df.top_half.str.split('-').str[0].astype('Int32')
        standings_df['th_losses'] = standings_df.top_half.str.split('-').str[1].astype('Int32')
        standings_df['ppg'] = round(standings_df.total_points / regular_season_end, 2)
        standings_df['season'] = s
        df = pd.concat([df, standings_df])


    most_m_wins = df[df.m_wins == df.m_wins.max()].sort_values(['season', 'team'])
    most_m_wins_row = (
        'Most Matchup Wins',
        str(most_m_wins.m_wins.iloc[0]),
        ', '.join(list(most_m_wins.team)),
        ', '.join(list(most_m_wins.season.astype(str))),
        ''
    )

    most_m_losses = df[df.m_losses == df.m_losses.max()].sort_values(['season', 'team'])
    most_m_losses_row = (
        'Most Matchup Losses',
        str(most_m_losses.m_losses.iloc[0]),
        ', '.join(list(most_m_losses.team)),
        ', '.join(list(most_m_losses.season.astype(str))),
        ''
    )

    most_th_wins = df[df.th_wins == df.th_wins.max()].sort_values(['season', 'team'])
    most_th_wins_row = (
        'Most Top Half Wins',
        str(most_th_wins.th_wins.iloc[0]),
        ', '.join(list(most_th_wins.team)),
        ', '.join(list(most_th_wins.season.astype(str))),
        ''
    )

    most_th_losses = df[df.th_losses == df.th_losses.max()].sort_values(['season', 'team'])
    most_th_losses_row = (
        'Most Top Half Losses',
        str(most_th_losses.th_losses.iloc[0]),
        ', '.join(list(most_th_losses.team)),
        ', '.join(list(most_th_losses.season.astype(str))),
        ''
    )

    most_ppg = df[df.ppg == df.ppg.max()].sort_values(['season', 'team'])
    most_ppg_row = (
        'Highest PPG',
        str(most_ppg.ppg.iloc[0]),
        ', '.join(list(most_ppg.team)),
        ', '.join(list(most_ppg.season.astype(str))),
        ''
    )

    least_ppg = df[df.ppg == df.ppg.min()].sort_values(['season', 'team'])
    least_ppg_row = (
        'Lowest PPG',
        str(least_ppg.ppg.iloc[0]),
        ', '.join(list(least_ppg.team)),
        ', '.join(list(least_ppg.season.astype(str))),
        ''
    )

    return pd.DataFrame([most_m_wins_row,
                         most_m_losses_row,
                         most_th_wins_row,
                         most_th_losses_row,
                         most_ppg_row,
                         least_ppg_row],
                        columns=['category', 'record', 'holder', 'season', 'week'])


def get_tophalf_records():
    """
    Calculate top half records:
    - Most/fewest
    - Closest win/loss
    - Largest disparity
    """

    matchups = Database(table='matchups').retrieve_data(how='all')[['season', 'week', 'team', 'score']]
    matchups = matchups.sort_values(['season', 'week', 'score'], ascending=False)
    matchups['med_rank'] = matchups.groupby(['season', 'week']).score.rank()
    matchups['med'] = matchups.groupby(['season', 'week']).score.transform('median')
    matchups['med_diff'] = abs(matchups.score - matchups.med)
    matchups['n_teams'] = matchups.groupby(['season', 'week']).team.transform('nunique') // 2

    # highest median score
    highest = matchups[matchups.med == matchups.med.max()]
    highest_teams = highest[(highest.med_rank == highest.n_teams) | (highest.med_rank == highest.n_teams+1)]
    season = highest.season.values[0]
    week = highest.week.values[0]
    holder_str = f'{highest_teams.team.values[0]} ({highest_teams.score.values[0]:.2f})-{highest_teams.team.values[1]} ({highest_teams.score.values[1]:.2f})'
    highest_row = ('Highest Median Score', f'{highest.med.max():.2f}', holder_str, season, week)

    # lowest median score
    lowest = matchups[matchups.med == matchups.med.min()]
    lowest_teams = lowest[(lowest.med_rank == lowest.n_teams) | (lowest.med_rank == lowest.n_teams+1)]
    season = lowest.season.values[0]
    week = lowest.week.values[0]
    holder_str = f'{lowest_teams.team.values[0]} ({lowest_teams.score.values[0]:.2f})-{lowest_teams.team.values[1]} ({lowest_teams.score.values[1]:.2f})'
    lowest_row = ('Lowest Median Score', f'{lowest.med.min():.2f}', holder_str, season, week)

    # closest tophalf matchup
    closest = matchups[matchups.med_diff.round(2) == round(matchups.med_diff.min(), 2)]
    holder_str = f'{closest.team.values[0]} ({closest.score.values[0]:.2f})-{closest.team.values[1]} ({closest.score.values[1]:.2f})'
    closest_row = ('Closest Top Half Matchup', f'{matchups.med_diff.min() * 2:.2f}', holder_str, closest.season.values[0], closest.week.values[0])

    # biggest tophalf matchup disparity
    furthest = matchups[(matchups.med_rank == matchups.n_teams) | (matchups.med_rank == matchups.n_teams+1)]
    furthest = furthest[furthest.med_diff == furthest.med_diff.max()]
    holder_str = f'{furthest.team.values[0]} ({furthest.score.values[0]:.2f})-{furthest.team.values[1]} ({furthest.score.values[1]:.2f})'
    furthest_row = ('Biggest Top Half Difference', f'{furthest.med_diff.max() * 2:.2f}', holder_str, furthest.season.values[0], furthest.week.values[0])

    return pd.DataFrame([
        highest_row,
        lowest_row,
        closest_row,
        furthest_row
    ],
        columns=['category', 'record', 'holder', 'season', 'week'])


def get_matchup_records(last_season):
    """
    Calculate matchup-related records:
    - Most/fewest points in a matchup
    - Closest matchup
    - Biggest blowout
    """
    # matchup records
    most_matchup_points = -999
    least_matchup_points = 999
    closest_matchup = 999
    biggest_blowout = -999
    for s in range(2018, last_season + 1):
        print(s)
        data = DataLoader(year=s)
        params = Params(data)
        teams = Teams(data)
        regular_season_end = params.regular_season_end
        matchups = data.matchups()
        for m in matchups['schedule']:
            week = m['matchupPeriodId']
            if week <= regular_season_end:
                # most total points
                tm1_score = m['away']['totalPoints']
                tm2_score = m['home']['totalPoints']
                total = round(tm1_score + tm2_score, 2)
                most_matchup_points_check = total > most_matchup_points
                if most_matchup_points_check:
                    most_matchup_points = total
                    tm1 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['away']['teamId'])
                    tm2 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['home']['teamId'])
                    holder_str = f'{tm1} ({tm1_score:.2f})-{tm2} ({tm2_score:.2f})'
                    most_points_row = ('Most Matchup Points', f'{total:.2f}', holder_str, s, week)

                least_points_check = total < least_matchup_points
                if least_points_check:
                    least_matchup_points = total
                    tm1 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['away']['teamId'])
                    tm2 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['home']['teamId'])
                    holder_str = f'{tm1} ({tm1_score:.2f})-{tm2} ({tm2_score:.2f})'
                    least_points_row = ('Fewest Matchup Points', f'{total:.2f}', holder_str, s, week)

                diff = abs(round(tm1_score - tm2_score, 2))
                closest_matchup_check = diff < closest_matchup
                if closest_matchup_check:
                    closest_matchup = diff
                    tm1 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['away']['teamId'])
                    tm2 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['home']['teamId'])
                    holder_str = f'{tm1} ({tm1_score:.2f})-{tm2} ({tm2_score:.2f})'
                    closest_matchup_row = ('Closest Matchup', f'{diff:.2f}', holder_str, s, week)

                biggest_blowout_check = diff > biggest_blowout
                if biggest_blowout_check:
                    biggest_blowout = diff
                    tm1 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['away']['teamId'])
                    tm2 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['home']['teamId'])
                    holder_str = f'{tm1} ({tm1_score:.2f})-{tm2} ({tm2_score:.2f})'
                    biggest_blowout_row = ('Biggest Blowout', f'{diff:.2f}', holder_str, s, week)

    return pd.DataFrame([
        most_points_row,
        least_points_row,
        closest_matchup_row,
        biggest_blowout_row
    ],
        columns=['category', 'record', 'holder', 'season', 'week'])


def get_per_stat_records(last_season):
    """
    Calculate player/team stat records:
    - Most yards (passing, rushing, receiving, total)
    - Most turnovers (INTs, fumbles, total)
    - Most TDs
    - Most receptions
    """
    pass_stats = [3]
    rush_stats = [24]
    rec_stats = [42, 53]
    to_stats = [20, 72]
    all_stats = flatten_list([pass_stats, rush_stats, rec_stats, to_stats])
    rows = [[] for stat in all_stats]
    records_dict = {constants.PLAYER_STATS_MAP[s]["display"]: -99 for s in all_stats}

    for s in range(2019, last_season + 1):
        print(s)
        data = DataLoader(year=s)
        teams = Teams(data=data)
        params = Params(data)
        regular_season_end = params.regular_season_end
        matchups = data.matchups()
        for m in matchups['schedule']:
            week = m['matchupPeriodId']
            if week <= regular_season_end:
                for tm in ['home', 'away']:
                    team = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m[tm]['teamId'])
                    stats = m[tm]['cumulativeScore']
                    for idx, (stat, row) in enumerate(zip(all_stats, rows)):
                        stat_name = constants.PLAYER_STATS_MAP[stat]['display']
                        try:
                            total = int(stats['scoreByStat'][str(stat)]['score'])
                            if total == records_dict[stat_name]:  # if total equals current record, append
                                rows[idx][2] += f', {team}'
                                rows[idx][3] += f', {s}'
                                rows[idx][4] += f', {week}'
                            if total > records_dict[stat_name]:  # if total is greater than current record, replace
                                records_dict[stat_name] = total
                                row = [f'Most {stat_name}', total, team, str(s), str(week)]
                                rows[idx] = row
                                print(row)
                        except KeyError:
                            continue

    return pd.DataFrame(
        rows,
        columns=['category', 'record', 'holder', 'season', 'week']
    )


def get_stat_group_records(last_season):
    """
    Calculate team stat totals
    """
    records_dict = {
        'Most Total Yards': [[3, 24, 42], -99],
        'Most Total Touchdowns': [[4, 25, 43, 93, 101, 102, 103, 104], -99],
        'Most Total Turnovers': [[20, 72], -99],
    }
    rows = [[] for k in records_dict]

    for s in range(2019, last_season + 1):
        print(s)
        data = DataLoader(year=s)
        teams = Teams(data=data)
        params = Params(data)
        regular_season_end = params.regular_season_end
        matchups = data.matchups()
        for m in matchups['schedule']:
            week = m['matchupPeriodId']
            if week <= regular_season_end:
                for tm in ['home', 'away']:
                    team = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m[tm]['teamId'])
                    stats = m[tm]['cumulativeScore']
                    for idx, (k, v) in enumerate(records_dict.items()):
                        total = 0
                        for st in v[0]:
                            total += int(stats['scoreByStat'][str(st)]['score'])
                        if total == records_dict[k][1]:  # if total equals current record, append
                            rows[idx][2] += f', {team})'
                            rows[idx][3] += f', {s}'
                            rows[idx][4] += f', {week}'
                        if total > records_dict[k][1]:  # if total is greater than current record, replace
                            records_dict[k][1] = total
                            row = [k, f'{total:,}', team, str(s), str(week)]
                            rows[idx] = row
                            print(row)

    return pd.DataFrame(
        rows,
        columns=['category', 'record', 'holder', 'season', 'week']
    )


def get_most_points_by_position(last_season):
    """
    Calculate most points by position (QB, RB, WR, TE, DST)
    """
    records_dict = {
        'Most QB Points': [0, -99],
        'Most RB Points': [2, -99],
        'Most WR Points': [4, -99],
        'Most TE Points': [6, -99],
        'Most DST Points': [16, -99]
    }
    rows = [[] for k in records_dict]

    for s in range(2018, last_season + 1):
        print(s)
        data = DataLoader(year=s)
        teams_info = Teams(data=data)
        params = Params(data)
        regular_season_end = params.regular_season_end
        for w in range(1, regular_season_end + 1):
            teams_data = data.load_week(w)['teams']
            for t in teams_data:
                team = teamid_to_name(ids=constants.TEAM_IDS, teams=teams_info, teamid=t['id'])
                for idx, (k, v) in enumerate(records_dict.items()):  # loop over each record type
                    for plr in t['roster']['entries']:  # loop over each player on team
                        if plr['lineupSlotId'] not in [20, 21, 22, 24, 25]:  # if player is in lineup
                            if v[0] in plr['playerPoolEntry']['player'][
                                'eligibleSlots']:  # if current position ID is in player's eligible slots
                                name = plr['playerPoolEntry']['player']['fullName']
                                for stat in plr['playerPoolEntry']['player']['stats']:  # loop over player stats
                                    if stat['scoringPeriodId'] == w and stat[
                                        'statSourceId'] == 0:  # if stat dict is in current week and is actual scores
                                        pts = stat['appliedTotal']
                                        if pts == records_dict[k][1]:  # if total equals current record, append
                                            rows[idx][2] += f', {team} ({name})'
                                            rows[idx][3] += f', {s}'
                                            rows[idx][4] += f', {w}'
                                        if pts > records_dict[k][1]:  # if total is greater than current record, replace
                                            records_dict[k][1] = pts  # update current record
                                            row = [k, f'{pts:.2f}', f'{team} ({name})', str(s), str(w)]
                                            rows[idx] = row
                                            print(row)

    return pd.DataFrame(
        rows,
        columns=['category', 'record', 'holder', 'season', 'week']
    )
