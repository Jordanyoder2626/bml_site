from scripts.utils import constants


EAST_DIVISION = {'Quinn', 'Caden', 'Jordan', 'Rendle', 'Luke'}
DIVISION_ALIASES = {
    'thomas': 'Rendle'
}


def active_team_names() -> list[str]:
    return [
        team['name']['display']
        for team in constants.TEAM_IDS.values()
        if team.get('active')
    ]


def team_division(team: str) -> str:
    team = DIVISION_ALIASES.get(team, team)
    return 'East' if team in EAST_DIVISION else 'West'


def sort_by_record(records: list[dict],
                   wins_key: str = 'wins',
                   points_key: str = 'score') -> list[dict]:
    return sorted(
        records,
        key=lambda x: (x[wins_key], x[points_key]),
        reverse=True
    )


def order_playoff_standings(records: list[dict],
                            wins_key: str = 'wins',
                            points_key: str = 'score',
                            playoff_teams: int = 5) -> list[dict]:
    active = [r for r in records if r['team'] in active_team_names()]

    division_winners = []
    for division in ['East', 'West']:
        division_teams = [
            r for r in active
            if team_division(r['team']) == division
        ]
        if division_teams:
            division_winners.append(
                sort_by_record(
                    division_teams,
                    wins_key=wins_key,
                    points_key=points_key
                )[0]
            )

    division_winners = sort_by_record(
        division_winners,
        wins_key=wins_key,
        points_key=points_key
    )

    winner_names = {r['team'] for r in division_winners}
    wild_cards = sort_by_record(
        [r for r in active if r['team'] not in winner_names],
        wins_key=wins_key,
        points_key=points_key
    )

    playoff_count = max(playoff_teams - len(division_winners), 0)
    playoff = division_winners + wild_cards[:playoff_count]
    remaining = wild_cards[playoff_count:]

    return playoff + remaining


def playoff_team_names(records: list[dict],
                       wins_key: str = 'wins',
                       points_key: str = 'score',
                       playoff_teams: int = 5) -> list[str]:
    return [
        r['team']
        for r in order_playoff_standings(
            records=records,
            wins_key=wins_key,
            points_key=points_key,
            playoff_teams=playoff_teams
        )[:playoff_teams]
    ]


def bye_games_back(records: list[dict], team: str,
                   wins_key: str = 'wins', points_key: str = 'score') -> float:
    """Signed record gap to either a division title or the final bye."""
    ordered = order_playoff_standings(records, wins_key, points_key)
    target = next(row for row in ordered if row['team'] == team)
    if len(ordered) <= 3:
        return 0
    # Holders measure their cushion over the first team outside the bye spots;
    # chasers measure their deficit to the final team inside them.
    holds_bye = any(row['team'] == team for row in ordered[:3])
    boundary = ordered[3] if holds_bye else ordered[2]
    wildcard_gap = boundary[wins_key] - target[wins_key]
    rivals = [row[wins_key] for row in ordered
              if row['team'] != team and team_division(row['team']) == team_division(team)]
    division_gap = max(rivals) - target[wins_key] if rivals else wildcard_gap
    return min(division_gap, wildcard_gap)


def bye_status(records: list[dict], team: str, weeks_left: int,
               wins_key: str = 'wins', points_key: str = 'score') -> str | None:
    """Conservative bye status with both division-title and wildcard routes.

    At the season's end use actual points. Before then, pessimistic/optimistic
    bounds leave unresolved points ties open and never assume a future result.
    """
    weeks_left = max(0, weeks_left)
    if weeks_left == 0:
        byes = order_playoff_standings(records, wins_key, points_key)[:3]
        return 'c' if any(row['team'] == team for row in byes) else 'x'
    for worst_case, status in ((True, 'c'), (False, 'x')):
        bound = []
        for record in records:
            row = record.copy()
            is_target = row['team'] == team
            if is_target != worst_case:
                row[wins_key] += weeks_left
            if is_target:
                row[points_key] = float('-inf') if worst_case else float('inf')
            bound.append(row)
        has_bye = any(row['team'] == team for row in
                      order_playoff_standings(bound, wins_key, points_key)[:3])
        if has_bye == worst_case:
            return status
    return None


def eliminated_from_postseason(records: list[dict], team: str, weeks_left: int,
                               bootyman: bool = False) -> bool:
    """Test the team's most favorable record/points bound for qualification."""
    remaining = max(0, weeks_left)
    bound = []
    for record in records:
        row = record.copy()
        is_target = row['team'] == team
        # To reach the Bowl, favor a target loss and wins by every rival.
        if (not is_target if bootyman else is_target):
            row['wins'] += remaining
        if is_target and remaining:
            row['score'] = float('-inf') if bootyman else float('inf')
        bound.append(row)
    ordered = order_bootyman_standings(bound) if bootyman else order_playoff_standings(bound)
    slots = 2 if bootyman else 5
    return not any(row['team'] == team for row in ordered[:slots])


def order_bootyman_standings(records: list[dict],
                             wins_key: str = 'wins',
                             points_key: str = 'score') -> list[dict]:
    active = [r for r in records if r['team'] in active_team_names()]

    return sorted(
        active,
        key=lambda x: (x[wins_key], x[points_key])
    )
