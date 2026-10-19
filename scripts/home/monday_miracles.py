"""Describe the remaining scoring needed to turn a trailing matchup into a win."""

from decimal import Decimal


def current_week_matchups(week_data, week):
    """ESPN may leave totalPoints at zero until the matchup is final."""
    matchups = []
    for matchup in week_data['schedule']:
        if matchup['matchupPeriodId'] != week or 'away' not in matchup:
            continue
        home, away = matchup['home'], matchup['away']

        def score(side):
            scores = side.get('pointsByScoringPeriod') or {}
            return scores.get(str(week), scores.get(week, side.get('totalPoints', 0)))

        matchups.append({'team1': home['teamId'], 'score1': score(home),
                         'team2': away['teamId'], 'score2': score(away)})
    return matchups


def _names(players):
    names = [player['player_name'] for player in players]
    if len(names) < 3:
        return ' and '.join(names)
    return ', '.join(names[:-1]) + ', and ' + names[-1]


def build_monday_miracles(matchups, lineups, probabilities, team_name):
    rows = []
    for matchup in matchups:
        if 'team2' not in matchup:
            continue
        score1 = Decimal(str(matchup['score1']))
        score2 = Decimal(str(matchup['score2']))
        if score1 == score2:
            continue
        trailing, leading = (
            (matchup['team1'], matchup['team2']) if score1 < score2
            else (matchup['team2'], matchup['team1'])
        )
        if not probabilities.get(trailing, 0) > 0:
            continue
        own = [p for p in lineups.get(trailing, {}).values()
               if p['remaining_fraction'] > 0]
        other = [p for p in lineups.get(leading, {}).values()
                 if p['remaining_fraction'] > 0]
        if not own and not other:
            continue
        deficit = f'{abs(score1 - score2):.2f}'
        if own:
            verb = 'needs' if len(own) == 1 else 'need'
            if other:
                requirement = (
                    f'{_names(own)} {verb} to outscore {_names(other)} '
                    f'by more than {deficit} points to win.'
                )
            else:
                combined = ' combined' if len(own) > 1 else ''
                requirement = (
                    f'{_names(own)} {verb} more than {deficit}{combined} '
                    'points to win.'
                )
        else:
            requirement = (
                f'{team_name(trailing)} has no players remaining and needs '
                f'{_names(other)} to lose more than {deficit} points to win.'
            )
        rows.append({'team': team_name(trailing),
                     'opponent': team_name(leading), 'requirement': requirement})
    return rows
