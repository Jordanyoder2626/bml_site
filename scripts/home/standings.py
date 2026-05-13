from typing import Any

import pandas as pd

from scripts.api.DataLoader import DataLoader
from scripts.utils.database import Database
from scripts.api.Settings import Params
from scripts.api.Teams import Teams
from scripts.utils import constants
from scripts.utils import league_rules
from scripts.utils import utils


class Standings:
    def __init__(self, season, week):
        self.season = season
        self.week = week
        self.data = DataLoader(year=self.season, week=self.week)
        self.teams = Teams(data=self.data)
        self.params = Params(data=self.data)
        self.standings_df = pd.DataFrame(columns=[
            'team',
            'overall',
            'overall_wins',
            'win_perc',
            'matchup',
            'top_half',
            'total_points',
            'division'
        ])

    @staticmethod
    def _format_weeks_back(value):
        """
        Weeks behind formatter for UI
        """
        if value == constants.CLINCHED:
            return constants.CLINCHED_DISP
        elif value == constants.ELIMINATED:
            return constants.ELIMINATED_DISP
        elif value < 0:
            return f'+{abs(value)}'
        elif value > 0:
            return f'{value}'
        else:
            return '-'

    @staticmethod
    def _format_points_back(value):
        """
        Points behind formatter for UI
        """
        if value < 0:
            return f'+{abs(value):.2f}'
        elif value == 0:
            return '-'
        else:
            return f'{value:.2f}'

    @staticmethod
    def _format_points(value):
        """
        Total points formatter for UI
        """
        return f'{value:,.2f}'

    def _clinch_bye(self,
                    row: pd.Series,
                    fourth_seed_wins: float) -> int | None:
        """
        Calculate if a team clinched playoff BYE week (top 3 seed)
        """
        weeks_ahead = (row.overall_wins - fourth_seed_wins)
        weeks_behind = row['wb2']

        if self.week - 1 <= self.params.regular_season_end:

            if weeks_ahead > self.params.weeks_left:
                return constants.CLINCHED

            elif weeks_behind > self.params.weeks_left:
                return constants.ELIMINATED

            else:
                return weeks_behind

        return None

    def _clinch_playoff(self,
                        row: pd.Series,
                        sixth_wins: float) -> int | None:
        """
        Calculate if a team clinched playoff spot week (top 5 seeds)
        """
        weeks_ahead = (row.overall_wins - sixth_wins)
        weeks_behind = row['wb5']

        if self.week - 1 <= self.params.regular_season_end:

            if weeks_ahead > self.params.weeks_left:
                return constants.CLINCHED

            elif weeks_behind > self.params.weeks_left:
                return constants.ELIMINATED

            else:
                return weeks_behind

        return None

    def _clinch_scenarios(self,
                          team_name: str,
                          seed: int) -> list[Any]:

        clinch_type = 'Bye' if seed == 3 else 'Playoffs'

        clinch_weeks_left = (
            self.params.regular_season_end - self.week
        )

        data = league_rules.order_playoff_standings(
            records=self.standings_df.to_dict(orient='records'),
            wins_key='overall_wins',
            points_key='total_points',
            playoff_teams=5
        )
        if len(data) <= seed:
            return []

        data_matches = [
            d for d in data
            if d['team'] == team_name
        ]
        if not data_matches:
            return []
        data_tm = data_matches[0]
        wb_column = 'wb2' if seed == 3 else f'wb{seed}'

        clinched = True if data_tm[wb_column] == -99 else False
        eliminated = True if data_tm[wb_column] == 99 else False

        if not (clinched or eliminated):

            rows = []

            if data_tm['seed'] <= seed:

                seed_plus_one_wins = data[seed]['overall_wins']

                for wins in range(-1, 2):

                    new_wb = (
                        (data_tm['overall_wins'] - seed_plus_one_wins)
                        + wins
                    )

                    if new_wb > clinch_weeks_left:

                        clinch_over_teams = ', '.join([
                            f'{d["team"]}'
                            for d in data
                            if d['team'] != team_name
                            and d['overall_wins'] == seed_plus_one_wins
                        ])

                        row = [
                            team_name,
                            clinch_type,
                            wins,
                            clinch_over_teams
                        ]

                        if row[-1] not in utils.flatten_list(rows):
                            rows.append(row)

            else:

                team_matches = [
                    i for i, data in enumerate(data)
                    if team_name in data['team']
                ]
                if not team_matches:
                    return rows
                team_idx = team_matches[0]

                seed_to_team = data[(seed - 1):team_idx]

                for team_to_clear in seed_to_team:

                    seed_wins = team_to_clear['overall_wins']

                    for wins in range(2):

                        new_wb = (
                            (data_tm['overall_wins'] - seed_wins)
                            + wins
                        )

                        if new_wb > clinch_weeks_left:

                            clinch_over_teams = ', '.join([
                                f'{d["team"]}'
                                for d in data
                                if d['team'] != team_name
                                and d['overall_wins'] == seed_wins
                            ])

                            row = [
                                team_name,
                                clinch_type,
                                wins,
                                clinch_over_teams
                            ]

                            if row[-1] not in utils.flatten_list(rows):
                                rows.append(row)

            return rows

    def _elim_scenarios(self,
                        team_name: str,
                        seed: int) -> list[Any]:

        elim_type = 'Bye' if seed == 3 else 'Playoffs'

        clinch_weeks_left = (
            self.params.regular_season_end - self.week
        )

        data = league_rules.order_playoff_standings(
            records=self.standings_df.to_dict(orient='records'),
            wins_key='overall_wins',
            points_key='total_points',
            playoff_teams=5
        )
        if len(data) < seed:
            return []

        data_matches = [
            d for d in data
            if d['team'] == team_name
        ]
        if not data_matches:
            return []
        data_tm = data_matches[0]
        wb_column = 'wb2' if seed == 3 else f'wb{seed}'

        clinched = True if data_tm[wb_column] == -99 else False
        eliminated = True if data_tm[wb_column] == 99 else False

        if not (clinched or eliminated):

            rows = []

            if data_tm['seed'] > seed:

                seed_wins = data[seed - 1]['overall_wins']

                all_seed_data = [
                    d for d in data
                    if d['overall_wins'] == seed_wins
                ]

                for _ in all_seed_data:

                    for wins in reversed(range(-1, 2)):

                        new_wb = (
                            (seed_wins - data_tm['overall_wins'])
                            - wins
                        )

                        if new_wb > clinch_weeks_left:

                            elim_by_teams = ', '.join([
                                f'{d["team"]}'
                                for d in data
                                if d['team'] != team_name
                                and d['overall_wins'] == seed_wins
                            ])

                            row = [
                                team_name,
                                elim_type,
                                wins,
                                elim_by_teams
                            ]

                            if row[-1] not in utils.flatten_list(rows):
                                rows.append(row)

            else:

                team_matches = [
                    i for i, data in enumerate(data)
                    if team_name in data['team']
                ]
                if not team_matches:
                    return rows
                team_idx = team_matches[0]

                team_to_seed = data[(team_idx + 1):(seed + 1)]

                for team_to_clear in team_to_seed:

                    seed_wins = team_to_clear['overall_wins']

                    for wins in range(-1, 2):

                        new_wb = (
                            (data_tm['overall_wins'] - seed_wins)
                            + wins
                        )

                        if new_wb > clinch_weeks_left:

                            elim_by_teams = ', '.join([
                                f'{d["team"]}'
                                for d in data
                                if d['team'] != team_name
                                and d['overall_wins'] == seed_wins
                            ])

                            row = [
                                team_name,
                                elim_type,
                                wins,
                                elim_by_teams
                            ]

                            if (
                                row[-1] not in utils.flatten_list(rows)
                            ) and (
                                len(row[-1].split(', '))
                                == len(team_to_seed)
                            ):
                                rows.append(row)

            return rows

    def _bootyman_scenarios(self,
                            team_name: str,
                            scenario_type: str) -> list[Any]:

        clinch_weeks_left = (
            self.params.regular_season_end - self.week
        )

        data = league_rules.order_bootyman_standings(
            records=self.standings_df.rename(
                columns={
                    'overall_wins': 'wins',
                    'total_points': 'score'
                }
            ).to_dict(orient='records'),
            wins_key='wins',
            points_key='score'
        )

        data_tm = [
            d for d in data
            if d['team'] == team_name
        ][0]

        rows = []

        if scenario_type == 'escape':
            boundary_wins = data[1]['wins']

            for wins in range(-1, 2):
                new_wb = (
                    (data_tm['wins'] - boundary_wins)
                    + wins
                )

                if new_wb > clinch_weeks_left:
                    escape_over_teams = ', '.join([
                        f'{d["team"]}'
                        for d in data
                        if d['team'] != team_name
                        and d['wins'] == boundary_wins
                    ])

                    row = [
                        team_name,
                        'Bootyman Bowl',
                        wins,
                        escape_over_teams,
                        scenario_type
                    ]

                    if row[-2] not in utils.flatten_list(rows):
                        rows.append(row)

        if scenario_type == 'clinch':
            boundary_wins = data[2]['wins']

            for wins in reversed(range(-1, 2)):
                new_wb = (
                    (boundary_wins - data_tm['wins'])
                    - wins
                )

                if new_wb > clinch_weeks_left:
                    clinch_with_teams = ', '.join([
                        f'{d["team"]}'
                        for d in data
                        if d['team'] != team_name
                        and d['wins'] == boundary_wins
                    ])

                    row = [
                        team_name,
                        'Bootyman Bowl',
                        wins,
                        clinch_with_teams,
                        scenario_type
                    ]

                    if row[-2] not in utils.flatten_list(rows):
                        rows.append(row)

        return rows

    def get_matchup_results(self,
                            week: int,
                            team_id: int) -> dict[str, Any]:

        display_name = utils.teamid_to_name(
            ids=constants.TEAM_IDS,
            teams=self.teams,
            teamid=team_id
        )

        db_id = (
            f'{self.season}_{str(week).zfill(2)}_{display_name}'
        )

        matchups = self.teams.team_schedule(team_id)

        matchups_filter = [
            {k: v for k, v in d.items()}
            for d in matchups
            if d.get('week') == week
        ]
        if not matchups_filter:
            return {}
        matchups_filter = matchups_filter[0]

        if matchups_filter.get('opponent'):

            opponent_display_name = utils.teamid_to_name(
                ids=constants.TEAM_IDS,
                teams=self.teams,
                teamid=matchups_filter['opponent']
            )

        else:
            opponent_display_name = None

        matchup_result = matchups_filter['result']

        score = matchups_filter['score']

        if matchups_filter.get('opponent_score'):
            opp_score = matchups_filter['opponent_score']
        else:
            opp_score = None

        return {
            'id': db_id,
            'season': self.season,
            'week': week,
            'team': display_name,
            'score': score,
            'opponent': opponent_display_name,
            'opponent_score': opp_score,
            'matchup_result': matchup_result,
            'top_half_result': 0
        }

    def format_standings(self) -> pd.DataFrame | None:
        """
        Create standings table for Flask UI

        - Top 5 teams make playoffs by standings
        """

        as_of_week = self.params.as_of_week

        matchups = (
            Database(
                table='matchups',
                season=self.season,
                week=self.week
            )
            .retrieve_data(how='season')
            .iloc[:, 0:-1]
        )

        matchups = (
            matchups[
                matchups.week <= self.params.regular_season_end
            ]
        )

        matchups = matchups.to_dict(orient='records')

        active_teams = set(league_rules.active_team_names())

        for team_id in self.teams.team_ids:

            display_name = utils.teamid_to_name(
                ids=constants.TEAM_IDS,
                teams=self.teams,
                teamid=team_id
            )

            if display_name not in active_teams:
                continue

            team_matchups = [
                m for m in matchups
                if m['team'] == display_name
                and m['week'] <= as_of_week
            ]

            m_wins = sum(
                d['matchup_result']
                for d in team_matchups
            )

            m_losses = as_of_week - m_wins

            m_record = f'{int(m_wins)}-{int(m_losses)}'

            th_record = '-'

            division_opponents = [
                team
                for team in active_teams
                if team != display_name
                and league_rules.team_division(team) == league_rules.team_division(display_name)
            ]
            division_matchups = [
                matchup
                for matchup in team_matchups
                if matchup['opponent'] in division_opponents
            ]
            division_wins = sum(
                matchup['matchup_result']
                for matchup in division_matchups
            )
            division_losses = len(division_matchups) - division_wins
            division_record = f'{int(division_wins)}-{int(division_losses)}'

            ov_wins = m_wins
            ov_losses = m_losses

            ov_record = m_record

            try:
                win_pct = f'{(ov_wins / as_of_week):.3f}'
            except ZeroDivisionError:
                win_pct = '0.000'

            total_points = round(
                sum(d['score'] for d in team_matchups),
                2
            )

            row = [
                display_name,
                ov_record,
                ov_wins,
                win_pct,
                m_record,
                th_record,
                total_points,
                division_record
            ]

            self.standings_df.loc[
                len(self.standings_df)
            ] = row

        ordered_teams = [
            r['team']
            for r in league_rules.order_playoff_standings(
                records=self.standings_df.rename(
                    columns={
                        'overall_wins': 'wins',
                        'total_points': 'score'
                    }
                ).to_dict(orient='records'),
                playoff_teams=5
            )
        ]

        self.standings_df = (
            self.standings_df
            .set_index('team')
            .reindex(ordered_teams)
            .reset_index()
        )

        self.standings_df['seed'] = range(
            1,
            len(self.standings_df) + 1
        )

        if len(self.standings_df) < 5:
            self.standings_df['wb2'] = 0
            self.standings_df['wb5'] = 0
            self.standings_df['total_points_disp'] = (
                self.standings_df.total_points.apply(
                    lambda x: self._format_points(x)
                )
            )
            self.standings_df['wb2_disp'] = '-'
            self.standings_df['wb5_disp'] = '-'
            return self.standings_df.reset_index(drop=True)

        bye_seed_wins = self.standings_df.iloc[2].overall_wins
        five_seed_wins = self.standings_df.iloc[4].overall_wins

        fourth_seed_wins = self.standings_df.iloc[3].overall_wins
        sixth_wins = self.standings_df.iloc[5].overall_wins if len(self.standings_df) > 5 else 0

        self.standings_df['wb2'] = (
            bye_seed_wins
            - self.standings_df.overall_wins
        )

        self.standings_df['wb5'] = (
            five_seed_wins
            - self.standings_df.overall_wins
        )

        self.standings_df['total_points_disp'] = (
            self.standings_df.total_points.apply(
                lambda x: self._format_points(x)
            )
        )

        self.standings_df['wb2'] = (
            self.standings_df.apply(
                lambda x: self._clinch_bye(
                    x,
                    fourth_seed_wins=fourth_seed_wins
                ),
                axis=1
            )
        )

        self.standings_df['wb2_disp'] = (
            self.standings_df.wb2.apply(
                lambda x: self._format_weeks_back(x)
            )
        )

        self.standings_df['wb5'] = (
            self.standings_df.apply(
                lambda x: self._clinch_playoff(
                    x,
                    sixth_wins=sixth_wins
                ),
                axis=1
            )
        )

        self.standings_df['wb5_disp'] = (
            self.standings_df.wb5.apply(
                lambda x: self._format_weeks_back(x)
            )
        )

        return self.standings_df.reset_index(drop=True)

    def clinching_scenarios(self):

        clinch_rows = []
        elim_rows = []
        bootyman_rows = []

        for team in self.teams.owner_ids:

            tm = constants.TEAM_IDS[team]['name']['display']

            bye_clinches = self._clinch_scenarios(
                team_name=tm,
                seed=3
            )

            bye_elims = self._elim_scenarios(
                team_name=tm,
                seed=3
            )

            playoffs_clinches = self._clinch_scenarios(
                team_name=tm,
                seed=5
            )

            playoffs_elims = self._elim_scenarios(
                team_name=tm,
                seed=5
            )

            bootyman_escapes = self._bootyman_scenarios(
                team_name=tm,
                scenario_type='escape'
            )

            bootyman_clinches = self._bootyman_scenarios(
                team_name=tm,
                scenario_type='clinch'
            )

            if bye_clinches:
                for bc_row in bye_clinches:
                    clinch_rows.append(bc_row)

            if bye_elims:
                for be_row in bye_elims:
                    elim_rows.append(be_row)

            if playoffs_clinches:
                for pc_row in playoffs_clinches:
                    clinch_rows.append(pc_row)

            if playoffs_elims:
                for pe_row in playoffs_elims:
                    elim_rows.append(pe_row)

            if bootyman_escapes:
                for bb_row in bootyman_escapes:
                    bootyman_rows.append(bb_row)

            if bootyman_clinches:
                for bb_row in bootyman_clinches:
                    bootyman_rows.append(bb_row)

        clinch_rows.sort(key=lambda x: (x[0], x[1]))
        elim_rows.sort(key=lambda x: (x[0], x[1]))
        bootyman_rows.sort(key=lambda x: (x[4], x[0]))

        return {
            'clinches': clinch_rows,
            'eliminations': elim_rows,
            'bootyman': bootyman_rows
        }
