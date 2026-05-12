import json
from datetime import datetime as dt

import pandas as pd

from scripts.api.DataLoader import DataLoader
from scripts.home.playoff_scenarios import PlayoffScenarios
from scripts.utils.database import Database
from scripts.api.Settings import Params
from scripts.api.Teams import Teams
from scripts.home.standings import Standings
from scripts.utils import constants
from scripts.utils import league_rules
import scripts.scenarios.scenarios as scenarios
from scripts.simulations import simulations
from scripts.efficiency.efficiencies import plot_efficiency


MANAGER_TO_TEAM_NAME = {
    team['name']['display']: team['name'].get('team_name', team['name']['display'])
    for team in constants.TEAM_IDS.values()
}


def display_team_name(name: str) -> str:
    return MANAGER_TO_TEAM_NAME.get(name, name)


def display_team_values(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    for column in columns:
        if column in df.columns:
            df[column] = df[column].map(display_team_name)
    return df


def display_team_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={
        column: display_team_name(column)
        for column in df.columns
    })


def display_team_list_rows(rows: list[list]) -> list[list]:
    return [
        [display_team_name(row[0]), *row[1:]]
        if row else row
        for row in rows
    ]


def _display_team_series(names: str) -> str:
    teams = [
        display_team_name(name.strip())
        for name in str(names).split(',')
        if name.strip()
    ]

    if len(teams) <= 1:
        return teams[0] if teams else ''
    if len(teams) == 2:
        return ' or '.join(teams)
    return f'{", ".join(teams[:-1])}, or {teams[-1]}'


def _net_result_phrase(net_wins: int, other_teams: str, scenario_type: str) -> str:
    other_teams = _display_team_series(other_teams)

    if scenario_type == 'clinch':
        if net_wins >= 1:
            return f'with a win and a loss by {other_teams}'
        if net_wins == 0:
            return f'with the same result or better than {other_teams}'
        return f'even with a loss if {other_teams} wins'

    if net_wins >= 1:
        return f'even with a win and a loss by {other_teams}'
    if net_wins == 0:
        return f'with the same result or worse than {other_teams}'
    return f'with a loss and a win by {other_teams}'


def _visible_probability(probability: str) -> bool:
    return str(probability).strip() != '0.0%'


def _team_verb(team_name: str, singular: str, plural: str) -> str:
    return plural if team_name.endswith('s') else singular


def format_scenario_statements(rows: list[list], scenario_type: str) -> list[list]:
    formatted_rows = []

    for row in rows:
        if len(row) < 5:
            continue

        team, target, net_wins, other_teams, probability = row[:5]
        if not _visible_probability(probability):
            continue

        display_team = display_team_name(team)
        verb = (
            _team_verb(display_team, 'clinches', 'clinch')
            if scenario_type == 'clinch'
            else _team_verb(display_team, 'is eliminated from', 'are eliminated from')
        )
        statement = (
            f'{display_team} {verb} {str(target).lower()} '
            f'{_net_result_phrase(int(net_wins), other_teams, scenario_type)}.'
        )
        formatted_rows.append([statement, probability])

    return formatted_rows


season = constants.SEASON
data = DataLoader(season)
params = Params(data)
teams = Teams(data)
week = params.regular_season_end+1 if params.current_week > params.regular_season_end+1 else params.current_week
previous_week = max(params.current_week - 1, 0)
power_data_week = previous_week
power_display_week = week
n_teams = len(teams.team_ids)

# load db tables
day = dt.now().strftime('%a')
the_week = params.as_of_week if day == 'Tue' else params.current_week  # Wed is start of new week, and season_sim runs on Tue
the_week = max(the_week, 1)
completed_week = max(min(params.as_of_week, params.regular_season_end), 0)
db_pr = Database(table='power_ranks', season=season, week=power_data_week)
betting_table = (
    Database(table='betting_table', season=season, week=params.current_week)
    .retrieve_data(how='season')  # show previous week on Tues
    .sort_values('created')
    .tail(n_teams)  # most recent db updates
)
season_sim_table = (
    Database(table='season_sim', season=season, week=week).
    retrieve_data(how='season')
    .sort_values('created')
    .tail(n_teams)  # most recent db updates
)
season_sim_wins_table = Database(table='season_sim_wins', season=season, week=the_week).retrieve_data(how='week')
season_sim_ranks_table = Database(table='season_sim_ranks', season=season, week=the_week).retrieve_data(how='week')
h2h_data = Database(table='h2h', season=season, week=completed_week).retrieve_data(how='season')
ss_data = Database(table='schedule_switcher', season=season, week=completed_week).retrieve_data(how='season')
alltime_df = Database(table='alltime_standings').retrieve_data(how='all')
records_df = Database(table='records').retrieve_data(how='all')


# HOME PAGE
standings = Standings(season=season, week=week)
standings_df = standings.format_standings()
clinches = standings.clinching_scenarios()
ps = PlayoffScenarios(data=data, params=params, teams=teams)
bye_scens = ps.get_new_clinches(seed=2)
playoff_scens = ps.get_new_clinches(seed=5)
magic_numbers = ps.get_magic_numbers()
standings_df['bye_magic_number'] = standings_df['team'].map(lambda t: magic_numbers.get(t, {}).get('bye', None))
standings_df['playoff_magic_number'] = standings_df['team'].map(lambda t: magic_numbers.get(t, {}).get('playoff', None))
standings_df['bye_status'] = standings_df.apply(
    lambda x: x.wb2_disp if x.wb2_disp in ['c', 'x'] else x.bye_magic_number,
    axis=1
)
standings_df['playoff_status'] = standings_df.apply(
    lambda x: x.wb5_disp if x.wb5_disp in ['c', 'x'] else x.playoff_magic_number,
    axis=1
)

def format_prob(p):
    if 0 < p <= 0.001:
        return "<0.1%"
    elif .999 <= p < 1:
        return ">99.9%"
    else:
        return f"{p*100:.1f}%"

for s in clinches['clinches']:
    if s[1] == 'Bye':
        try:
            prob = format_prob(bye_scens[s[0]]['p_clinch'])
        except KeyError:
            prob = f'0.0%'
        s.extend([prob])
    else:
        try:
            prob = format_prob(playoff_scens[s[0]]['p_clinch'])
        except KeyError:
            prob = f'0.0%'
        s.extend([prob])

for s in clinches['eliminations']:
    if s[1] == 'Bye':
        try:
            prob = format_prob(bye_scens[s[0]]['p_elim'])
        except KeyError:
            prob = f'0.0%'
        s.extend([prob])
    else:
        try:
            prob = format_prob(playoff_scens[s[0]]['p_elim'])
        except KeyError:
            prob = f'0.0%'
        s.extend([prob])
# TODO: fix last week clinches/elims. for wild card, net wins and probability should be blank (or save all sims to get prob of team getting outscored by x pts)

standings_df = display_team_values(standings_df, ['team'])
clinches['clinches'] = format_scenario_statements(
    clinches['clinches'],
    scenario_type='clinch'
)
clinches['eliminations'] = format_scenario_statements(
    clinches['eliminations'],
    scenario_type='eliminate'
)


pr_data = db_pr.retrieve_data(how='season')
pr_data[['power_score_norm', 'score_norm_change']] = round(pr_data[['power_score_norm', 'score_norm_change']] * 100).astype('Int32')
pr_table = pr_data[pr_data.week == power_data_week]
pr_table = pr_table.sort_values('power_score_raw', ascending=False)
pr_table['rank_change'] = -pr_table.rank_change
pr_table[['total_points', 'weekly_points', 'consistency', 'manager', 'luck']] = pr_table[['season_idx', 'week_idx', 'consistency_idx', 'manager_idx', 'luck_idx']].rank(ascending=False, method='min').astype('Int32')
pr_cols = ['team', 'total_points', 'weekly_points', 'consistency', 'manager', 'luck', 'power_rank', 'rank_change', 'power_score_norm', 'score_norm_change']
pr_table = display_team_values(pr_table, ['team'])
pr_data = display_team_values(pr_data, ['team'])
rank_data = pr_data[['team', 'week', 'power_rank', 'power_score_norm']].sort_values(['week', 'power_score_norm'], ascending=[True, False]).to_dict(orient='records')
rank_data = json.dumps(rank_data, indent=2)
rank_data = {'rank_data': rank_data}


# SIMULATIONS PAGE
if betting_table.empty:
    timestamp_betting = 'No data'
    betting_table = pd.DataFrame(columns=['team', 'avg_score', 'p_win', 'p_tophalf', 'p_highest', 'p_lowest'])
else:
    timestamp_betting = pd.to_datetime(betting_table.created.values[0]).strftime("%A, %b %d %Y")
    betting_table = betting_table.sort_values(['matchup_id', 'avg_score'])
    betting_table['avg_score'] = betting_table.avg_score.round(2).apply(lambda x: f'{x:.2f}')
    betting_table['p_win'] = betting_table.p_win.apply(lambda x: simulations.calculate_odds(init_prob=x))
    betting_table['p_tophalf'] = betting_table.p_tophalf.apply(lambda x: simulations.calculate_odds(init_prob=x))
    betting_table['p_highest'] = betting_table.p_highest.apply(lambda x: simulations.calculate_odds(init_prob=x))
    betting_table['p_lowest'] = betting_table.p_lowest.apply(lambda x: simulations.calculate_odds(init_prob=x))
    betting_table = display_team_values(betting_table, ['team'])

keep_cols = ['team', 'projected_wins', 'projected_losses', 'total_points', 'playoffs', 'finals', 'champion']
if season_sim_table.empty:
    timestamp_season_sim = 'No data'
    season_sim_table = pd.DataFrame(columns=keep_cols)
    season_sim_wins_table = pd.DataFrame(columns=['Team'])
    season_sim_ranks_table = pd.DataFrame(columns=['Team'])
else:
    timestamp_season_sim = pd.to_datetime(season_sim_table.created.values[0]).strftime("%A, %b %d %Y")
    season_sim_table[['playoffs', 'finals', 'champion']] = (season_sim_table[['playoffs', 'finals', 'champion']]*100).round(0).astype(int).astype(str) + '%'
    season_sim_table[['matchup_wins', 'tophalf_wins', 'total_wins', 'total_points']] = season_sim_table[['matchup_wins', 'tophalf_wins', 'total_wins', 'total_points']].round(1)
    season_sim_table['projected_wins'] = season_sim_table.matchup_wins.round(1)
    season_sim_table['projected_losses'] = (params.regular_season_end - season_sim_table.matchup_wins).round(1)
    season_sim_table['total_points'] = season_sim_table.total_points.apply(lambda x: f'{x:,.1f}')
    teams_order = [
        record['team']
        for record in league_rules.order_playoff_standings(
            records=[
                {
                    'team': row.team,
                    'wins': row.matchup_wins,
                    'score': float(str(row.total_points).replace(',', ''))
                }
                for _, row in season_sim_table.iterrows()
            ],
            playoff_teams=5
        )
    ]
    season_sim_table = season_sim_table.set_index('team')
    season_sim_table = season_sim_table.reindex(teams_order).reset_index()[keep_cols]

    order = season_sim_table.team.tolist()
    season_sim_table = display_team_values(season_sim_table, ['team'])
    if season_sim_wins_table.empty:
        season_sim_wins_table = pd.DataFrame(columns=['Team'])
    else:
        season_sim_wins_table['p_str'] = round(season_sim_wins_table.p * 100).astype(int)
        season_sim_wins_table = season_sim_wins_table[['team', 'wins', 'p_str']].pivot(index='team', columns='wins', values='p_str').fillna('')
        season_sim_wins_table = season_sim_wins_table.reindex(order).reset_index().rename(columns={'team': 'Team'})
        season_sim_wins_table = display_team_values(season_sim_wins_table, ['Team'])

    if season_sim_ranks_table.empty:
        season_sim_ranks_table = pd.DataFrame(columns=['Team'])
    else:
        season_sim_ranks_table['p_str'] = round(season_sim_ranks_table.p * 100).astype(int)
        season_sim_ranks_table = season_sim_ranks_table[['team', 'ranks', 'p_str']].pivot(index='team', columns='ranks', values='p_str').fillna('')
        season_sim_ranks_table = season_sim_ranks_table.reindex(order).reset_index().rename(columns={'team': 'Team'})
        season_sim_ranks_table = display_team_values(season_sim_ranks_table, ['Team'])


# SCENARIOS PAGE
h2h_data = h2h_data[h2h_data.week <= completed_week] if 'week' in h2h_data.columns else h2h_data
total_wins = scenarios.get_total_wins(h2h_data=h2h_data, teams=teams, week=completed_week + 1)
wins_by_week = scenarios.get_wins_by_week(h2h_data=h2h_data, total_wins=total_wins, teams=teams)
wins_vs_opp = scenarios.get_wins_vs_opp(h2h_data=h2h_data, total_wins=total_wins, wins_by_week=wins_by_week, week=completed_week + 1)
wins_vs_opp = display_team_columns(display_team_values(wins_vs_opp, ['team']))
wins_by_week = display_team_values(wins_by_week, ['team'])

ss_disp_temp = scenarios.get_schedule_switcher_display(ss_data=ss_data, total_wins=total_wins, week=completed_week + 1)
ss_luck_dict = scenarios.calculate_schedule_luck(ss_data)
if ss_luck_dict:
    ss_luck = pd.DataFrame.from_dict(ss_luck_dict, orient='index').reset_index().rename(columns={'index':'team', 0:'Luck'})
else:
    ss_luck = pd.DataFrame({'team': total_wins.team, 'Luck': '+0.0'})
ss_disp = pd.merge(ss_disp_temp, ss_luck, on='team')
ss_disp = display_team_columns(display_team_values(ss_disp, ['team']))


# TEAM EFFICIENCY PAGE
eff_plot = plot_efficiency(
    season=season,
    week=previous_week,
    x='actual_lineup_score',
    y='optimal_lineup_score',
    xlab='Difference From Optimal Points per Week',
    ylab='Optimal Points per Week',
    title=''
)

# HISTORY/CHAMPIONS PAGE
champs = pd.read_csv(r'champions.csv').sort_values('Season', ascending=False)
prev_champs = champs[['Season', 'Team', 'Runner Up']]

champ_count = (
    pd.concat(
        [
            champs.groupby('Team').size().rename('First'),
            champs.groupby('Runner Up').size().rename('Second')
        ], axis=1
    )
    .fillna(0)
    .sort_values('First', ascending=False)
)

champ_count['First'] = champ_count.First.apply(
    lambda n: ''.join(
        [
            f'<i class="fa fa-trophy icon-gold"></i>{"" if (i + 1) % 3 else "<span><br></span>"}' for i in range(int(n))
        ]
    ) + '<br>'
)
champ_count['Second'] = champ_count.Second.apply(
    lambda n: ''.join(
        [
            f'<i class="fa fa-trophy" style="color: #C0C0C0"></i>{"" if (i + 1) % 3 else "<span><br></span>"}' for i in range(int(n))
        ]
    ) + '<br>'
)
champ_count = champ_count.reset_index().rename(columns={'index': 'Team'})
