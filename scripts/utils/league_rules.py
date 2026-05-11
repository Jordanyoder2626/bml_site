from scripts.utils import constants


EAST_DIVISION = {'Quinn', 'Caden', 'Jordan', 'Rendle', 'Luke'}


def active_team_names() -> list[str]:
    return [
        team['name']['display']
        for team in constants.TEAM_IDS.values()
        if team.get('active')
    ]


def team_division(team: str) -> str:
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
