from itertools import product

from scripts.utils.database import Database
from scripts.utils import constants
from scripts.utils import league_rules


class PlayoffScenarios:
    def __init__(self, data, params, teams):
        self.data = data
        self.params = params
        self.teams = teams

        self.season = constants.SEASON
        self.team_names = league_rules.active_team_names()

        self.standings = self._load_standings()
        self.betting_table = self._load_betting_table()
        self.matchups = self._load_matchups()
        self.scenarios = self._get_scenarios()

    @staticmethod
    def _sort_standings(standings: list[dict]) -> list[dict]:
        return league_rules.order_playoff_standings(
            records=standings,
            wins_key='wins',
            points_key='score',
            playoff_teams=5
        )

    @staticmethod
    def _sort_bootyman_standings(standings: list[dict]) -> list[dict]:
        return league_rules.order_bootyman_standings(
            records=standings,
            wins_key='wins',
            points_key='score'
        )

    def _load_standings(self) -> list[dict]:
        df = Database(
            table='matchups',
            season=self.season,
            week=self.params.as_of_week
        ).retrieve_data(how='season')
        df = df[df.team.isin(self.team_names)]
        df['wins'] = df.matchup_result

        standings = (
            df[['team', 'score', 'wins']]
            .groupby('team')
            .sum()
            .reset_index()
        )
        standings['losses'] = df.week.max() - standings.wins

        return self._sort_standings(standings.to_dict(orient='records'))

    def _load_betting_table(self) -> list[dict]:
        df = (
            Database(
                table='betting_table',
                season=self.season,
                week=self.params.current_week
            )
            .retrieve_data(how='season')
            .sort_values('created')
            .tail(len(self.team_names))
        )
        df = df[df.team.isin(self.team_names)]
        return df[['team', 'matchup_id', 'p_win']].to_dict(orient='records')

    def _teamid_to_display(self, teamid: int) -> str:
        return constants.TEAM_IDS[
            self.teams.teamid_to_primowner[teamid]
        ]['name']['display']

    def _load_matchups(self) -> list[tuple[str, str]]:
        probability_teams = {row['team'] for row in self.betting_table}
        matchups = []

        for matchup in self.data.matchups()['schedule']:
            if matchup['matchupPeriodId'] != self.params.current_week:
                continue
            if 'away' not in matchup:
                continue

            home = self._teamid_to_display(teamid=matchup['home']['teamId'])
            away = self._teamid_to_display(teamid=matchup['away']['teamId'])

            if home not in self.team_names or away not in self.team_names:
                continue
            if home not in probability_teams or away not in probability_teams:
                continue

            matchups.append((home, away))

        return matchups

    def _get_scenarios(self) -> list[dict]:
        h2h_outcomes = list(product([0, 1], repeat=len(self.matchups)))
        all_scenarios = []

        for h2h in h2h_outcomes:
            week_winners = {
                'matchup': {name: 0 for name in self.team_names},
            }

            for i, (home, away) in enumerate(self.matchups):
                winner = home if h2h[i] == 0 else away
                week_winners['matchup'][winner] += 1

            week_winners['p'] = self._matchup_weight(week_winners)
            all_scenarios.append(week_winners)

        return [s for s in all_scenarios if s['p'] > 0]

    def _matchup_weight(self, scenario: dict[str, dict]) -> float:
        matchup_prob = 1.0

        for home, away in self.matchups:
            home_wins = scenario['matchup'][home] == 1
            home_probs = [
                o for o in self.betting_table
                if o['team'] == home
            ]
            home_prob = home_probs[0]['p_win'] if home_probs else 0.5
            matchup_prob *= home_prob if home_wins else (1 - home_prob)

        return matchup_prob

    def get_teams(self, standings: list[dict], seed: int) -> tuple[list[str], list[str]]:
        standings = self._sort_standings(standings)
        games_played = standings[0]['wins'] + standings[0]['losses']
        weeks_left = self.params.regular_season_end - games_played

        clinched = {}
        eliminated = {}
        clinch_idx = min(seed, len(standings) - 1)
        eliminated_idx = min(seed - 1, len(standings) - 1)

        for team in standings:
            clinched[team['team']] = (
                team['wins'] - standings[clinch_idx]['wins'] > weeks_left
            )
            eliminated[team['team']] = (
                standings[eliminated_idx]['wins'] - team['wins'] > weeks_left
            )

        return (
            [team for team, value in clinched.items() if value],
            [team for team, value in eliminated.items() if value]
        )

    def get_new_clinches(self, seed: int) -> dict:
        clinched, eliminated = self.get_teams(
            standings=self.standings,
            seed=seed
        )
        results = {
            name: {
                'clinched': 0,
                'eliminated': 0,
                'p_clinch': 0,
                'p_elim': 0,
                'clinch_scenarios': [],
                'elim_scenarios': []
            }
            for name in self.team_names
        }

        for scenario in self.scenarios:
            new_standings = []

            for team in self.standings:
                name = team['team']
                new_wins = team['wins'] + scenario['matchup'][name]
                new_standings.append({
                    'team': name,
                    'wins': new_wins,
                    'losses': (self.params.as_of_week + 1) - new_wins,
                    'score': round(team['score'], 2),
                })

            new_clinched, new_elim = self.get_teams(
                standings=new_standings,
                seed=seed
            )
            new_clinched = [team for team in new_clinched if team not in clinched]
            new_elim = [team for team in new_elim if team not in eliminated]

            for team in self.team_names:
                if team in new_clinched:
                    results[team]['clinched'] += 1
                    results[team]['p_clinch'] += scenario['p']
                    results[team]['clinch_scenarios'].append(scenario)

                if team in new_elim:
                    results[team]['eliminated'] += 1
                    results[team]['p_elim'] += scenario['p']
                    results[team]['elim_scenarios'].append(scenario)

        return {
            team: result
            for team, result in results.items()
            if result['clinched'] > 0 or result['eliminated'] > 0
        }

    def get_bootyman_status(self, standings: list[dict]) -> tuple[list[str], list[str]]:
        standings = self._sort_bootyman_standings(standings)
        games_played = standings[0]['wins'] + standings[0]['losses']
        weeks_left = self.params.regular_season_end - games_played

        clinched = {}
        escaped = {}
        second_worst = standings[1]
        third_worst = standings[2]

        for team in standings:
            clinched[team['team']] = (
                third_worst['wins'] - team['wins'] > weeks_left
            )
            escaped[team['team']] = (
                team['wins'] - second_worst['wins'] > weeks_left
            )

        return (
            [team for team, value in clinched.items() if value],
            [team for team, value in escaped.items() if value]
        )

    def get_new_bootyman_scenarios(self) -> dict:
        clinched, escaped = self.get_bootyman_status(
            standings=self.standings
        )
        results = {
            name: {
                'clinched': 0,
                'escaped': 0,
                'p_clinch': 0,
                'p_escape': 0,
                'clinch_scenarios': [],
                'escape_scenarios': []
            }
            for name in self.team_names
        }

        for scenario in self.scenarios:
            new_standings = []

            for team in self.standings:
                name = team['team']
                new_wins = team['wins'] + scenario['matchup'][name]
                new_standings.append({
                    'team': name,
                    'wins': new_wins,
                    'losses': (self.params.as_of_week + 1) - new_wins,
                    'score': round(team['score'], 2),
                })

            new_clinched, new_escaped = self.get_bootyman_status(
                standings=new_standings
            )
            new_clinched = [team for team in new_clinched if team not in clinched]
            new_escaped = [team for team in new_escaped if team not in escaped]

            for team in self.team_names:
                if team in new_clinched:
                    results[team]['clinched'] += 1
                    results[team]['p_clinch'] += scenario['p']
                    results[team]['clinch_scenarios'].append(scenario)

                if team in new_escaped:
                    results[team]['escaped'] += 1
                    results[team]['p_escape'] += scenario['p']
                    results[team]['escape_scenarios'].append(scenario)

        return {
            team: result
            for team, result in results.items()
            if result['clinched'] > 0 or result['escaped'] > 0
        }

    def team_magic_number(self, team: str, playoff_spots: int) -> int | None:
        team = team.title()[:4]
        matches = [s for s in self.standings if s['team'] == team]
        if not matches or len(self.standings) < playoff_spots:
            return None

        the_team = matches[0]
        current_losses = int(the_team['losses'])
        leading_team_wins = self.standings[playoff_spots - 1]['wins']

        if the_team['wins'] >= leading_team_wins:
            return None

        return (
            self.params.regular_season_end
            + 1
            - leading_team_wins
            - current_losses
        )

    def get_magic_numbers(self) -> dict[str, dict[str, int]]:
        magic_numbers = {
            team: {
                'bye': None,
                'playoff': None
            }
            for team in self.team_names
        }

        for team in self.team_names:
            for seed in [2, 5]:
                cat = 'bye' if seed == 2 else 'playoff'
                magic = self.team_magic_number(
                    team=team,
                    playoff_spots=seed
                )
                magic_numbers[team][cat] = '-' if magic is None or magic <= 0 else int(magic)

        return magic_numbers
