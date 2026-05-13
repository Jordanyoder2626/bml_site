from scripts.api.DataLoader import DataLoader
from scripts.api.Settings import Params
from scripts.api.Teams import Teams
from scripts.utils import constants
from scripts.home.playoff_scenarios import PlayoffScenarios


season = constants.SEASON
data = DataLoader(season)
params = Params(data)
teams = Teams(data)
ps = PlayoffScenarios(data=data, params=params, teams=teams)
bye_scens = ps.get_new_clinches(seed=3)
playoff_scens = ps.get_new_clinches(seed=5)
magic_numbers = ps.get_magic_numbers()


# clinching/elimination scenarios and probabilities
for team, res in playoff_scens.items():
    wins_needed = {t:[] for t in teams.teams}
    if res['eliminated']:
        print(f'{team} has a {round(res['p_elim'] * 100, 2)}% chance of being ELIMINATED from a playoff spot')

    if res['clinched']:
        print(f'{team} has a {round(res['p_clinch'] * 100, 2)}% chance of CLINCHING a playoff spot')


# describe a scenario
def xxdescribe_scenario(scenario: dict) -> str:
    parts = []
    m_winners = [t for t, r, in scenario['matchup'].items() if r == 1]
    th_winners = [t for t, r, in scenario['tophalf'].items() if r == 1]
    for home, away in ps.matchups:
        h2h_winner = home if home in m_winners else away
        parts.append(f"{h2h_winner} beats {away if h2h_winner == home else home}")  # handle ties in week_wins (both beat/lost median equally)
    parts.append(f"Top Half winners: {', '.join(sorted(th_winners)) or 'none'}")
    final = "\n".join(parts)
    return final
print(xxdescribe_scenario(ps.scenarios[40]))


# get a full summary
# TODO need to check against 3/7 seed wins
# steps: remove teams that have 0, 1 and 2 wins. identify relevant scenario for remaining teams (same # wins, <2, >0)
def describe_team_clinch_scenario(team: str, scenario: dict) -> str:
    if scenario[team]['clinched']:
        wins = [x['wins'] for x in ps.standings if x['team'] == team][0]
        if ps.params.current_week < ps.params.regular_season_end:
            check_teams = [s['team'] for s in ps.standings if 0 >= (s['wins'] - wins) >= -2*ps.params.weeks_left]  # check against trailing teams within two games
        else:
            check_teams = [s['team'] for s in ps.standings if 2*ps.params.weeks_left >= (s['wins'] - wins) >= -2*ps.params.weeks_left]  # for final week, need to check if teams ahead can be passed
        all_scens = {
            t: [] for t in check_teams
        }
        if len(check_teams) > 1:
            for r in scenario[team]['clinch_scenarios']:
                m = {t: v for t, v in r['matchup'].items() if t in check_teams}
                th = {t: v for t, v in r['tophalf'].items() if t in check_teams}
                for tm in check_teams:
                    if tm != team:
                        all_scens[tm].append((m[team] + th[team]) - (m[tm] + th[tm]))
            scenarios = []
            for tm in check_teams:
                tm_can_win = [str(w) for w in set(all_scens[tm])]
                if 0 < len(tm_can_win) < 3:
                    scenarios.append(f'{team} wins net {' or '.join(tm_can_win)} games over {tm}')
            r = scenario[team]
            makes = r['clinched']
            print(f"{team} CLINCHES in {makes}/{len(ps.scenarios)} scenarios ({100 * makes / len(ps.scenarios):.1f}%) -- {r['p_clinch']*100:.2f}% probability")
            print(f'{team} Clinches if: \n\t{'\n\tAND '.join(scenarios)}')
            print()
describe_team_clinch_scenario(team='Aide', scenario=playoff_scens)


# TODO: need to check against 2/5 seed wins
def describe_team_elim_scenario(team: str, scenario: dict) -> str:
    if scenario[team]['eliminated']:
        wins = [x['wins'] for x in ps.standings if x['team'] == team][0]
        if ps.params.current_week < ps.params.regular_season_end:
            check_teams = [s['team'] for s in ps.standings if 0 <= (s['wins'] - wins) <= 2*(ps.params.weeks_left-1)]  # check against leading teams within two games
        else:
            check_teams = [s['team'] for s in ps.standings if 2*ps.params.weeks_left >= (s['wins'] - wins) >= -2*ps.params.weeks_left]  # for final week, need to check if teams behind can be passed
        all_scens = {
            t: [] for t in check_teams
        }
        if len(check_teams) > 1:
            for r in scenario[team]['elim_scenarios']:
                m = {t: v for t, v in r['matchup'].items() if t in check_teams}
                th = {t: v for t, v in r['tophalf'].items() if t in check_teams}
                for tm in check_teams:
                    if tm != team:
                        all_scens[tm].append((m[team] + th[team]) - (m[tm] + th[tm]))
            scenarios = []
            for tm in check_teams:
                if 0 < len(set(all_scens[tm])) < 6:
                    scenarios.append(f'{team} wins net {min(all_scens[tm])} games over {tm}')
            r = scenario[team]
            misses = r['eliminated']
            print(f"{team} ELIMINATED in {misses}/{len(ps.scenarios)} scenarios ({100 * misses / len(ps.scenarios):.1f}%) -- {r['p_elim']*100:.1f}% probability")
            print(f'{team} Eliminated if: \n\t{'\n\tAND '.join(scenarios)}')
            print()
describe_team_elim_scenario(team='Adit', scenario=bye_scens)
