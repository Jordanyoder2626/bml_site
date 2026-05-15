from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.api.DataLoader import DataLoader
from scripts.utils import constants


@dataclass(frozen=True)
class BootymanConfig:
    weeks: tuple[int, ...]
    regular_season_end: int
    require_head_to_head: bool = True


BOOTYMAN_CONFIGS = {
    season: BootymanConfig(weeks=(13, 14), regular_season_end=12)
    for season in range(2018, 2021)
}
BOOTYMAN_CONFIGS.update({
    season: BootymanConfig(weeks=(14, 15), regular_season_end=13)
    for season in range(2021, 2025)
})
BOOTYMAN_CONFIGS[2025] = BootymanConfig(
    weeks=(15,),
    regular_season_end=14,
    require_head_to_head=False
)


def _team_name_lookup(data: dict[str, Any]) -> dict[int, str]:
    lookup = {}

    for team in data.get('teams', []):
        team_id = team['id']
        owner_id = team.get('primaryOwner')
        configured = constants.TEAM_IDS.get(owner_id, {})
        display = configured.get('name', {}).get('display')

        if not display:
            display = team.get('location') or team.get('name') or f'Team {team_id}'

        lookup[team_id] = display

    return lookup


def _iter_matchup_teams(matchup: dict[str, Any]):
    for side in ('home', 'away'):
        if side in matchup:
            yield matchup[side]['teamId'], float(matchup[side].get('totalPoints', 0))


def _regular_season_standings(schedule: list[dict[str, Any]],
                              regular_season_end: int) -> dict[int, dict[str, float]]:
    standings: dict[int, dict[str, float]] = {}

    for matchup in schedule:
        week = matchup.get('matchupPeriodId')
        if week is None or week > regular_season_end:
            continue
        if 'home' not in matchup or 'away' not in matchup:
            continue

        home_id = matchup['home']['teamId']
        away_id = matchup['away']['teamId']
        home_score = float(matchup['home'].get('totalPoints', 0))
        away_score = float(matchup['away'].get('totalPoints', 0))

        for team_id, score in [(home_id, home_score), (away_id, away_score)]:
            standings.setdefault(team_id, {'wins': 0.0, 'points': 0.0})
            standings[team_id]['points'] += score

        if home_score > away_score:
            standings[home_id]['wins'] += 1
        elif away_score > home_score:
            standings[away_id]['wins'] += 1
        else:
            standings[home_id]['wins'] += 0.5
            standings[away_id]['wins'] += 0.5

    return standings


def _bootyman_teams(schedule: list[dict[str, Any]],
                    regular_season_end: int) -> list[int]:
    standings = _regular_season_standings(
        schedule=schedule,
        regular_season_end=regular_season_end
    )
    ordered = sorted(
        standings.items(),
        key=lambda item: (item[1]['wins'], item[1]['points'])
    )
    return [team_id for team_id, _ in ordered[:2]]


def _bootyman_scores(schedule: list[dict[str, Any]],
                     bootyman_teams: list[int],
                     weeks: tuple[int, ...],
                     require_head_to_head: bool = True) -> tuple[dict[int, float], list[dict[str, Any]]]:
    scores = {team_id: 0.0 for team_id in bootyman_teams}
    matchup_rows = []
    bootyman_team_set = set(bootyman_teams)

    for matchup in schedule:
        if matchup.get('matchupPeriodId') not in weeks:
            continue

        matchup_scores = {
            team_id: score
            for team_id, score in _iter_matchup_teams(matchup)
            if team_id in scores
        }
        if not matchup_scores:
            continue
        if require_head_to_head and set(matchup_scores) != bootyman_team_set:
            continue

        for team_id, score in matchup_scores.items():
            if team_id in scores:
                scores[team_id] += score

        matchup_rows.append({
            'week': matchup.get('matchupPeriodId'),
            'scores': matchup_scores,
        })

    return scores, matchup_rows


def _format_score(score: float) -> str:
    return f'{score:.2f}'.rstrip('0').rstrip('.')


def _format_result(row: dict[str, str]) -> str:
    return (
        f"{row['Season']}: {row['Team']} "
        f"({_format_score(float(row['Score']))}) lost to "
        f"{row['Runner Up']} ({_format_score(float(row['Runner Up Score']))}) "
        f"in week(s) {row['Weeks']}"
    )


def _print_matchup_rows(matchup_rows: list[dict[str, Any]],
                        team_names: dict[int, str],
                        require_head_to_head: bool) -> None:
    if not require_head_to_head:
        rows_by_week = {}
        for matchup in matchup_rows:
            week_scores = rows_by_week.setdefault(matchup['week'], {})
            week_scores.update(matchup['scores'])
        matchup_rows = [
            {'week': week, 'scores': scores}
            for week, scores in sorted(rows_by_week.items())
        ]

    for matchup in matchup_rows:
        scores = ' vs. '.join(
            f'{team_names[team_id]} {_format_score(score)}'
            for team_id, score in matchup['scores'].items()
        )
        print(f"  Week {matchup['week']}: {scores}")


def generate_rows(start_season: int,
                  end_season: int,
                  listed_team_is_low_score: bool = True) -> list[dict[str, str]]:
    rows = []

    for season in range(start_season, end_season + 1):
        config = BOOTYMAN_CONFIGS[season]
        loader = DataLoader(year=season)
        schedule = loader.matchups()['schedule']
        team_names = _team_name_lookup(loader.teams())
        bootyman_teams = _bootyman_teams(
            schedule=schedule,
            regular_season_end=config.regular_season_end
        )
        scores, matchup_rows = _bootyman_scores(
            schedule=schedule,
            bootyman_teams=bootyman_teams,
            weeks=config.weeks,
            require_head_to_head=config.require_head_to_head
        )

        if len([score for score in scores.values() if score > 0]) != 2:
            found_scores = ', '.join(
                f'{team_names.get(team_id, team_id)}={_format_score(score)}'
                for team_id, score in scores.items()
            )
            raise RuntimeError(
                f'Could not find Bootyman Bowl scores for {season} '
                f'in weeks {", ".join(map(str, config.weeks))}. '
                f'Found: {found_scores}.'
            )

        ordered = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=not listed_team_is_low_score
        )
        listed_team_id, listed_team_score = ordered[0]
        runner_up_id, runner_up_score = ordered[1]

        row = {
            'Season': str(season),
            'Team': team_names[listed_team_id],
            'Runner Up': team_names[runner_up_id],
            'Score': _format_score(listed_team_score),
            'Runner Up Score': _format_score(runner_up_score),
            'Weeks': ','.join(str(week) for week in config.weeks),
        }
        print(_format_result(row))
        _print_matchup_rows(
            matchup_rows=matchup_rows,
            team_names=team_names,
            require_head_to_head=config.require_head_to_head
        )
        rows.append(row)

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate Bootyman Bowl results from ESPN matchup scores.'
    )
    parser.add_argument('--start-season', type=int, default=2018)
    parser.add_argument('--end-season', type=int, default=2025)
    parser.add_argument(
        '--output',
        default='bootyman_bowl.csv',
        help='CSV output path. Defaults to bootyman_bowl.csv.',
    )
    parser.add_argument(
        '--low-score-wins',
        action='store_true',
        help='Treat the lower Bootyman Bowl score as the listed team. This is the default.',
    )
    parser.add_argument(
        '--high-score-wins',
        action='store_true',
        help='Treat the higher Bootyman Bowl score as the listed team.',
    )
    parser.add_argument(
        '--include-scores',
        action='store_true',
        help='Include Score, Runner Up Score, and Weeks columns.',
    )
    args = parser.parse_args()

    rows = generate_rows(
        start_season=args.start_season,
        end_season=args.end_season,
        listed_team_is_low_score=not args.high_score_wins
    )

    output = Path(args.output)
    fieldnames = ['Season', 'Team', 'Runner Up']
    if args.include_scores:
        fieldnames.extend(['Score', 'Runner Up Score', 'Weeks'])

    with output.open('w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=fieldnames,
            extrasaction='ignore'
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f'Wrote {output}')


if __name__ == '__main__':
    main()
