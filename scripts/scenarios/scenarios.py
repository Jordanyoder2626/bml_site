from scripts.api.Teams import Teams
from scripts.utils import constants as const
import scripts.utils.utils as ut

import pandas as pd


def get_h2h(teams: Teams, season: int, week: int):
    """
    Create the h2h dataframe to use
    """
    tms = teams.team_ids
    df = pd.DataFrame(columns=['id', 'season', 'week', 'team', 'opp', 'result'])
    for tm1 in tms:
        for tm2 in tms:
            owner1 = teams.teamid_to_primowner[tm1]
            owner2 = teams.teamid_to_primowner[tm2]
            tm1_display = const.TEAM_IDS[owner1]['name']['display']
            tm2_display = const.TEAM_IDS[owner2]['name']['display']
            if tm1 == tm2:
                result = 0.0
            else:
                score1 = teams.team_scores(team_id=tm1)[week-1]
                score2 = teams.team_scores(team_id=tm2)[week-1]
                result = 1.0 if score1 > score2 else 0.5 if score1 == score2 else 0.0

            tm_id = f'{season}_{str(week).zfill(2)}_{tm1_display}_{tm2_display}'
            row = [tm_id, season, week, tm1_display, tm2_display, result]
            df.loc[len(df)] = row
    return df


def get_total_wins(h2h_data: pd.DataFrame,
                   teams: Teams,
                   week):
    """
    Calculate team's total wins: sum of wins against all teams for each week
    """
    end = week-1

    total_wins = h2h_data.groupby('team').result.sum().reset_index()
    total_wins['losses'] = (((len(teams.team_ids)-1) * end) - total_wins.result)
    total_wins['record'] = total_wins.result.astype('Int32').astype(str) + '-' + total_wins.losses.astype('Int32').astype(str)
    total_wins['win_perc'] = total_wins.result / ((len(teams.team_ids) -1 ) * end)
    total_wins['win_perc'] = total_wins.win_perc.map('{:.3f}'.format)
    return total_wins[['team', 'result', 'record', 'win_perc']]


def get_wins_by_week(h2h_data: pd.DataFrame,
                     total_wins: pd.DataFrame,
                     teams: Teams):
    """
    Calculate team's record vs league median for each week
    """
    wins_by_week = h2h_data.groupby(['team', 'week']).result.sum().reset_index()
    wins_by_week['losses'] = (len(teams.team_ids) -1) - wins_by_week.result
    wins_by_week['record'] = wins_by_week.result.astype('Int32').astype(str) + '-' + wins_by_week.losses.astype('Int32').astype(str)
    best_str = f'{int(wins_by_week.result.max())}-{int(wins_by_week.result.min())}'
    worst_str = f'{int(wins_by_week.result.min())}-{int(wins_by_week.result.max())}'
    wins_by_week_p = wins_by_week.pivot(index='team', columns='week', values='record')
    wins_by_week_p['weeks_best'] = (wins_by_week_p == best_str).sum(axis=1).astype(str)
    wins_by_week_p['weeks_worst'] = (wins_by_week_p == worst_str).sum(axis=1).astype(str)
    return (
        pd.merge(wins_by_week_p, total_wins, on='team')
        .sort_values('result', ascending=False)
        .drop(columns=['result', 'record', 'win_perc'], axis=1)
    )


def get_wins_vs_opp(h2h_data: pd.DataFrame,
                    total_wins: pd.DataFrame,
                    wins_by_week: pd.DataFrame,
                    week):
    """
    Calculate team's record if he played every team each week
    """
    end = week-1

    wins_vs_opp = h2h_data.groupby(['team', 'opponent']).result.sum().reset_index()
    wins_vs_opp['losses'] = end - wins_vs_opp.result
    wins_vs_opp['record'] = wins_vs_opp.result.astype('Int32').astype(str) + '-' + wins_vs_opp.losses.astype('Int32').astype(str)
    wins_vs_opp_p = wins_vs_opp.pivot(index='team', columns='opponent', values='record')
    wins_vs_opp_final = pd.merge(wins_vs_opp_p, total_wins, on='team').sort_values('win_perc', ascending=False)
    col_order = ut.flatten_list([['team'], wins_by_week.team.to_list(), ['record', 'win_perc']])
    wins_vs_opp_final = wins_vs_opp_final[col_order].set_index('team')
    for i in range(min(wins_vs_opp_final.shape)):
        # blank out diagonals where teams intersect
        wins_vs_opp_final.iloc[i, i] = ''
    return wins_vs_opp_final.reset_index()


def schedule_switcher(teams: Teams,
                      season: int,
                      week: int):
    """
    Create the schedule switcher dataframe
    """
    tms = teams.team_ids
    df = pd.DataFrame(columns=['id', 'season', 'week', 'team', 'schedule_of', 'result'])
    for schedule_of in tms:
        for team_switch in tms:
            # if schedule_of != team_switch:
            owner1 = teams.teamid_to_primowner[schedule_of]
            owner2 = teams.teamid_to_primowner[team_switch]
            schedule_of_display = const.TEAM_IDS[owner1]['name']['display']
            team_switch_display = const.TEAM_IDS[owner2]['name']['display']

            # get sched_of team's schedule
            schedule_of_schedule = teams.team_schedule(schedule_of)[week-1]

            # switch sched_of team with t_switch
            tm_sched = teams.team_schedule(team_switch)[week-1]
            score = tm_sched['score']
            new_opp_tm = schedule_of_schedule['opponent']
            new_opp_score = schedule_of_schedule['opponent_score']

            # if team and new opp are the same, need to use actual schedule results
            if team_switch != new_opp_tm:
                result = 1.0 if score > new_opp_score else 0.5 if score == new_opp_score else 0.0
            else:
                result = tm_sched['result']

            tm_id = f'{season}_{str(week).zfill(2)}_{team_switch_display}_{schedule_of_display}'
            row = [tm_id, season, week, team_switch_display, schedule_of_display, result]
            df.loc[len(df)] = row
    return df


def calculate_schedule_luck(ss_data: pd.DataFrame):
    """
    Calculate each team's schedule luck: difference of a teams' actual matchup wins and the average number of wins using all other schedules.
    Positive values indicate team is luckier
    """
    teams = set(ss_data.team)
    luck = {}
    for t in teams:
        ss_t = ss_data[ss_data.team == t]
        wins_act = ss_t[ss_t.schedule_of == t].result.sum()
        wins_exp = ss_t[ss_t.schedule_of != t].result.mean() * len(set(ss_data.week))
        diff = (wins_act - wins_exp)
        luck[t] = f'{"+" if diff >= 0 else ""}{diff:.1f}'
    return dict(sorted(luck.items(), key=lambda item: float(item[1]), reverse=True))


def get_schedule_switcher_display(ss_data: pd.DataFrame,
                                  total_wins: pd.DataFrame,
                                  week):
    """
    Format schedule switcher table for display on website.
    """
    end = week-1

    ss_data = ss_data.groupby(['team', 'schedule_of']).result.sum().reset_index()
    ss_data['losses'] = end - ss_data.result
    ss_data['record'] = ss_data.result.astype('Int32').astype(str) + '-' + ss_data.losses.astype('Int32').astype(str)
    ss_data_p = ss_data.pivot(index='team', columns='schedule_of', values='record')
    ss_data_final = pd.merge(ss_data_p, total_wins, on='team').sort_values('win_perc', ascending=False)
    col_order = ut.flatten_list([['team'], ss_data_final.team.to_list()])
    ss_data_final = ss_data_final[col_order].set_index('team')
    for irow, row in ss_data_final.iterrows():
        # bold diagonals where teams intersect
        for icol, col in enumerate(ss_data_final.columns):
            if irow == col:
                ss_data_final.loc[irow, col] = f'<span class="diagonal">{row[col]}</span>'
    return ss_data_final.reset_index()
