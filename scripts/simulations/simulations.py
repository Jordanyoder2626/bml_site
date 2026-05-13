from scripts.utils.utils import teamid_to_name
from scripts.api.DataLoader import DataLoader
from scripts.utils.database import Database
from scripts.api.Settings import Params
from scripts.api.Rosters import Rosters
from scripts.api.Teams import Teams
from scripts.utils import constants
from scripts.utils import league_rules

import scipy.stats as st
import pandas as pd
import numpy as np
import difflib
import random
pd.options.mode.chained_assignment = None


def _match_player_to_espn(the_player: str,
                          players: list) -> int | None:
    """
    Matches a name to ESPN's database and returns a player ID

    Args:
        the_player: a player's full name, position, and team abbreviation (ex: Full Name|Pos|TM)
        players: list of players to match on from ESPN using same format as the_player

    Returns:
        matching ESPN player ID
    """

    player_lookup = []
    for p in players:
        try:
            pl_name = p['player']['fullName']
            pl_pos = constants.POSITION_MAP[list(set(constants.POSITION_MAP) & set(p['player']['eligibleSlots']))[0]]
            pl_team = constants.NFL_TEAM_MAP[p['player']['proTeamId']]
            pl_lookup = f"{pl_name}|{pl_pos}|{pl_team}"
        except (KeyError, IndexError):
            continue
        player_lookup.append(pl_lookup)

    calc = [difflib.SequenceMatcher(None, the_player, m).ratio() for m in player_lookup]
    if max(calc) > 0.8:
        match_idx = calc.index(max(calc))
        return players[match_idx]['id']
    else:
        return None


def get_week_projections(week: int) -> pd.DataFrame:
    """Return Fantasy Pros projections for all positions"""

    data = DataLoader()
    players = data.players_info()['players']
    positions = ['qb', 'rb', 'wr', 'te', 'k']

    projections = pd.DataFrame()
    for pos in positions:
        url = f"https://www.fantasypros.com/nfl/projections/{pos}.php?scoring=HALF&week={week}"
        # url = f"https://www.fantasypros.com/nfl/rankings/half-point-ppr-{pos}.php?scoring=HALF&week={week}"
        df = pd.read_html(url)[0]

        # drop multi index column
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel()

        df['POSITION'] = pos.upper()
        try:
            df = df[['Player', 'FPTS', 'REC', 'POSITION']]
        except:
            df = df[['Player', 'FPTS', 'POSITION']]
            df['REC'] = 0

        # remove team from player name
        if pos != 'dst':
            df['TEAM'] = df.Player.str[-3:].str.strip()
            df['Player'] = df['Player'].str[:-3]
            df['Player'] = df['Player'].str.rstrip()

        if pos == 'dst':
            df['Player'] = df['Player'].str.split().str[-1] + ' DST'
            df['TEAM'] = ''

        projections = pd.concat([projections, df])

    projections['season'] = constants.SEASON
    projections['week'] = week
    projections.columns = [c.lower() for c in projections.columns]

    qb_mask = (projections.position == 'QB') & (projections.fpts > 10)
    rb_mask = (projections.position == 'RB') & (projections.fpts > 5)
    wr_mask = (projections.position == 'WR') & (projections.fpts > 5)
    te_mask = (projections.position == 'TE') & (projections.fpts > 3)
    k_mask = (projections.position == 'K') & (projections.fpts > 3)
    projections = projections[qb_mask | rb_mask | wr_mask | te_mask | k_mask]

    # match player to ESPN
    projections['match_on'] = projections.player + '|' + projections.position + '|' + projections.team
    projections['id'] = (projections.player.str.replace(r'[^a-zA-Z0-9]', '', regex=True)
                         + '_' + projections.season.astype(str)
                         + '_' + projections.week.astype(str).str.zfill(2))

    projections['espn_id'] = projections.apply(
        lambda x: _match_player_to_espn(x['match_on'], players), axis=1
    ).astype('Int64')

    return projections[~projections.espn_id.isnull()]


def query_projections_db(season: int,
                         week: int) -> pd.DataFrame:
    with Database() as conn:
        c = conn.cursor()
        query = f'''
        SELECT *
        FROM player_projections
        WHERE season={season} and week={week};
        '''
        c.execute(query)
        result = c.fetchall()
        if not result:
            return pd.DataFrame(columns=['name', 'espn_id', 'projection'])
        df = pd.DataFrame(result)
        df.columns = [col[0] for col in c.description]
    return df[['name', 'espn_id', 'projection']]


def calculate_best_lineup(team_roster: dict,
                          rosters: Rosters,
                          n_flex: int = None):
    positions = constants.POSITION_MAP
    slot_limits = rosters.slot_limits
    n_flex = n_flex if n_flex is not None else slot_limits.get(23, 2)
    selected = []
    for position_id, position in positions.items():
        # loop thru positions to get best projected lineup
        try:
            position_limit = slot_limits[position_id]
            position_played = [p for p in team_roster.items() if p[1]['slot_id'] == position_id and p[1]['played'] == 1]  # take out players who played
            selected.extend([p[0] for p in position_played])
            position_player_pool = {k: v for k, v in team_roster.items() if v['position'] == position and v['played'] == 0}
            remaining = position_limit-len(position_played)
            selector: list = sorted(
                position_player_pool,
                key=lambda x: position_player_pool[x]['projection'],
                reverse=True
            )[0:remaining]  # highest projected player(s)
            selected.extend(selector)  # remove player from available pool
        except KeyError:  # position is not used
            pass

    # get flex players
    flex_played = {k: v for k, v in team_roster.items() if v['slot_id'] == 23 and v['played'] == 1}
    if len(flex_played) > 0:
        selected.extend(list(flex_played.keys()))

    remaining_flex = max(n_flex - len(flex_played), 0)
    if remaining_flex > 0:
        flex_pool = {k: v for k, v in team_roster.items() if k not in selected and v['position_id'] in [2, 4, 6]}  # RB, WR, TE
        flex_selector = sorted(flex_pool, key=lambda x: flex_pool[x]['projection'], reverse=True)[0:remaining_flex]
        selected.extend(flex_selector)

    # best projected lineup
    lineup = {k: v
              for k, v
              in team_roster.items()
              if k in selected}
    return lineup


def get_best_lineup(week_data: dict,
                    rosters: Rosters,
                    params: Params,
                    replacement_players: dict[float],
                    projections: list[dict],
                    week: int,
                    team_id: int,
                    use_actuals: bool = True) -> dict:
    """
    Calculate a team's best lineup using projections from Fantasy Pros

    Args:
        week_data: ESPN data for the selected week
        params: league settings from class
        rosters: roster settings from class
        projections: data from Fantasy Pros
        week: current NFL week
        team_id: team to calculate lineup for
        replacement_players: average of top free agents if team cannot field a full lineup

    Returns:
        dictionary containing the team's best projected players
    """

    slots = constants.SLOTCODES
    positions = constants.POSITION_MAP
    team_data = [t for t in week_data['teams'] if t['id'] == team_id][0]
    roster = {}
    position_id = 0
    position = ''
    for plr in team_data['roster']['entries']:
        # general player data
        player_id = plr['playerId']
        player_name = plr['playerPoolEntry']['player']['fullName']
        slot_id = plr['lineupSlotId']
        lineup_slot = slots[slot_id]
        player_positions = plr['playerPoolEntry']['player']['eligibleSlots']
        for p in player_positions:
            # get NFL position
            try:
                position = positions[p]
                position_id = p
            except KeyError:
                continue

        # get actual and projected scores
        actual = 0
        projection = 0
        played = 0
        for stat in plr['playerPoolEntry']['player']['stats']:
            if stat['scoringPeriodId'] == week:
                if (
                    use_actuals
                    and stat['seasonId'] == constants.SEASON
                    and stat['scoringPeriodId'] == week
                    and stat['statSourceId'] == 0
                ):
                    actual = stat['appliedTotal']
                    played = 1
                try:
                    projection = [
                        {k:v for k,v in d.items()}
                        for d in projections
                        if d['espn_id'] == player_id
                    ][0]['projection']
                except IndexError:
                    # use ESPN projection if player is not found
                    if stat['statSourceId'] == 1:
                        projection = stat['appliedTotal']

        if projection > 0:
            roster[player_id] = {
                'player_name': player_name,
                'slot_id': slot_id,
                'lineup_slot': lineup_slot,
                'position_id': position_id,
                'position': position,
                'actual': actual,
                'projection': projection,
                'played': played
            }

    # check if roster is full, if not fill with replacement player
    roster_non_ir = {k: v for k, v in roster.items() if v['slot_id'] != 21}  # can't put IR player in lineup
    if len(roster_non_ir) < params.roster_size:
        for position in ['QB', 'RB', 'WR', 'TE', 'K']:
            pos_dict = {k: v for k, v in roster.items() if v['position'] == position}
            pos_id = [k for k, v in rosters.slotcodes.items() if v == position][0]
            limit = rosters.slot_limits.get(pos_id, 0)
            if limit == 0:
                continue

            if len(pos_dict) < limit:
                needed = limit - len(pos_dict)
                for i in range(1, needed + 1):
                    player_id = int(str(-1 * i) + str(pos_id))
                    roster[player_id] = {
                        'player_name': 'Free Agent',
                        'slot_id': pos_id,
                        'lineup_slot': position,
                        'position_id': position_id,
                        'position': position,
                        'actual': 0,
                        'projection': replacement_players[position],
                        'played': 0
                    }

        flex_limit = rosters.slot_limits.get(23, 2)
        flex_eligible = {
            k: v for k, v in roster.items()
            if v['position'] in ['RB', 'WR', 'TE']
        }
        required_flex_pool = (
            rosters.slot_limits.get(2, 0)
            + rosters.slot_limits.get(4, 0)
            + rosters.slot_limits.get(6, 0)
            + flex_limit
        )

        if len(flex_eligible) < required_flex_pool:
            needed = required_flex_pool - len(flex_eligible)
            best_flex_replacement = max(
                ['RB', 'WR', 'TE'],
                key=lambda p: replacement_players[p]
            )
            pos_id = [k for k, v in rosters.slotcodes.items() if v == best_flex_replacement][0]

            for i in range(1, needed + 1):
                player_id = int(str(-1 * i) + '23' + str(pos_id))
                roster[player_id] = {
                    'player_name': 'Free Agent',
                    'slot_id': 23,
                    'lineup_slot': 'Flex',
                    'position_id': pos_id,
                    'position': best_flex_replacement,
                    'actual': 0,
                    'projection': replacement_players[best_flex_replacement],
                    'played': 0
                }

    return calculate_best_lineup(team_roster=roster, rosters=rosters)


def simulate_lineup(lineup: dict) -> float:
    """Simulate a team's total score using the best projected lineup"""

    gamma_map = constants.GAMMA_VALUES  # found by fitting curve to each position using data from 2021-2024
    projected_points = 0.0
    for _, player in lineup.items():
        if player['played']:
            # add players who played first
            sim = player['actual']
            projected_points += sim
        else:
            # add players yet to play
            gamma_values = gamma_map.get(player['position'])
            if gamma_values:
                loc = gamma_values['loc'] + (player['projection'] - gamma_values['mean'])
                sim = st.gamma.rvs(a=gamma_values['a'], loc=loc, scale=gamma_values['scale'], size=1).item()
                # TODO: figure out a way to use a player's variance to adjust scale
            else:
                sim = player['projection']

            projected_points += sim
    return projected_points


def simulate_matchup(week_data: DataLoader,
                     rosters: Rosters,
                     params: Params,
                     replacement_players: dict[float],
                     week: int,
                     matchups: list[dict],
                     projections: list[dict],
                     use_actuals: bool = True) -> list[dict]:
    """
    Simulate matchups of two teams

    Args:
        week_data: ESPN data for the selected week
        rosters: roster settings from class
        params: league settings from class
        replacement_players: average of top free agents if team cannot field a full lineup
        week: week of matchup to simulate
        matchups: matchups for the selected week
        projections: Fantasy Pros projections for the selected week

    Returns:
        game id, team, simulated score, and simulated result for each team
    """

    matchup_sim = []
    for idx, m in enumerate(matchups):
        game_id = idx + 1  # used to group matchups for website

        team1 = m['team1']
        lineup1 = get_best_lineup(week_data=week_data,
                                  rosters=rosters,
                                  params=params,
                                  replacement_players=replacement_players,
                                  projections=projections,
                                  week=week,
                                  team_id=team1,
                                  use_actuals=use_actuals)
        sim1 = simulate_lineup(lineup1)

        if 'team2' in m:
            team2 = m['team2']
            lineup2 = get_best_lineup(week_data=week_data,
                                      rosters=rosters,
                                      params=params,
                                      replacement_players=replacement_players,
                                      projections=projections,
                                      week=week,
                                      team_id=team2,
                                      use_actuals=use_actuals)
            sim2 = simulate_lineup(lineup2)

            # redo sim if they are somehow tied
            if sim1 == sim2:
                sim1 = simulate_lineup(lineup1)
                sim2 = simulate_lineup(lineup2)

            matchup_sim.append({
                'game_id': game_id,
                'team': team1,
                'score': sim1,
                'result': 1 if sim1 > sim2 else 0
            })

            matchup_sim.append({
                'game_id': game_id,
                'team': team2,
                'score': sim2,
                'result': 1 if sim2 > sim1 else 0
            })
        else:
            # team has no opponent (playoff bye)
            matchup_sim.append({
                'game_id': game_id,
                'team': team1,
                'score': sim1,
                'result': 1
            })
    return matchup_sim


def simulate_week(week_data: DataLoader,
                  teams: Teams,
                  rosters: Rosters,
                  params: Params,
                  replacement_players: dict[float],
                  matchups: list,
                  projections: list[dict],
                  week: int,
                  n_sims: int = 10,
                  use_actuals: bool = True) -> list:
    """Simulate a week n_sims times and calculate number of occurrences for each category below"""

    # initialize counters
    n_scores  = {key: 0 for key in teams.team_ids}
    n_wins    = {key: 0 for key in teams.team_ids}
    n_tophalf = {key: 0 for key in teams.team_ids}
    n_highest = {key: 0 for key in teams.team_ids}
    n_lowest  = {key: 0 for key in teams.team_ids}
    for i, sim in enumerate(range(n_sims)):
        # if i % 1000 == 0: print(f'{i+1}/{n_sims}', end='\r')
        random.seed(random.randrange(n_sims))
        matchup_sim = simulate_matchup(week_data=week_data,
                                       rosters=rosters,
                                       params=params,
                                       replacement_players=replacement_players,
                                       week=week,
                                       matchups=matchups,
                                       projections=projections,
                                       use_actuals=use_actuals)

        # update counters after simulation
        for team in matchup_sim:
            n_scores[team['team']] += team['score']
            if team['result'] == 1:
                n_wins[team['team']] += 1

        for_tophalf = sorted(matchup_sim, key=lambda d: d['score'], reverse=True)[:int((len(teams.team_ids)/2))]
        for team in for_tophalf:
            n_tophalf[team['team']] += 1

        n_highest[max(matchup_sim, key=lambda x: x['score'])['team']] += 1
        n_lowest[min(matchup_sim, key=lambda x: x['score'])['team']] += 1

    return [n_scores, n_wins, n_tophalf, n_highest, n_lowest]


def calculate_odds(init_prob: dict) -> dict:
    """Convert counters from simulation into american odds"""

    # init_prob = sim_value / n_sims
    # round off very likely and unlikely events, less than 10/100,000
    if init_prob >= 0.9999:
        return '&#x2713;'  # check mark
    elif init_prob <= 0.0001:
        return '-'
    else:
        try:
            if init_prob >= 0.5:
                odds = (-1 * init_prob / (1 - init_prob)) * 100
                return f'{max(-10000, round(odds / 5) * 5)}'  # round to nearest 5
            else:
                odds = (1 * (1 - init_prob) / init_prob) * 100
                return f'+{min(10000, round(odds / 5) * 5)}'  # round to nearest 5
        except ZeroDivisionError:  # init_prob = 1 or 0
            if init_prob == 1:
                return '&#x2713;'  # check mark
            else:
                return '-'


def get_matchup_id(teams: Teams,
                   week: int,
                   team_id: int):
    """Get ESPN matchup ID for a team's matchup to display in UI table"""
    for m in teams._fetch_matchups():
        if m['week'] == week:
            if m.get('team1') == team_id or m.get('team2') == team_id:
                if m.get('team2'):
                    matchup_id = int((len(teams.team_ids) / 2) - ((week * len(teams.team_ids) / 2) - m['matchup_id']))
                    return matchup_id
                else:
                    # no team2 > team1 has playoff bye
                    return 99


def get_replacement_players(data: DataLoader,
                            n: int = 3):
    players_data = data.players_info()

    # first get all free agents
    free_agents = []
    position = ''
    for player in players_data['players']:
        if player['onTeamId'] == 0:
            player_id = player['id']
            player_name = player['player']['fullName']
            for pos in player['player']['eligibleSlots']:
                if pos in constants.POSITION_MAP:
                    position = constants.POSITION_MAP[pos]

            projection = 0
            if 'stat' in player['player']:
                for stat in player['player']['stats']:
                    if stat['seasonId'] == 2025 and stat['scoringPeriodId'] == 0 and stat['statSourceId'] == 1:
                        projection = stat['appliedAverage']

            try:
                free_agents.append({
                    'id': player_id,
                    'name': player_name,
                    'position': position,
                    'projection': projection
                })
            except NameError:
                pass

    # get replacement player score - average of top 3
    pos_dict = {}
    for position in ['QB', 'RB', 'WR', 'TE', 'K']:
        pos_fa = [fa for fa in free_agents if fa['position'] == position]
        top_n = sorted(pos_fa, key=lambda x: x['projection'], reverse=True)[:n]
        pos_dict[position] = sum(p['projection'] for p in top_n) / n

    return pos_dict


def get_ros_projections(data: DataLoader,
                        params: Params,
                        teams: Teams,
                        rosters: Rosters,
                        replacement_players: dict[float] = None):
    """Get rest of season projections from ESPN for all rostered players"""

    projections_dict = {}
    for week in range(params.current_week, 17+1):
        week_data = data.load_week(week)
        team_dict = {}
        for team in week_data['teams']:
            roster_dict = {}
            projection = 0
            position_id = 0
            position = ''
            team_name = teamid_to_name(
                ids=constants.TEAM_IDS,
                teams=teams,
                teamid=team['id']
            )
            for player in team['roster']['entries']:
                player_id = player['playerId']
                team_id = player['playerPoolEntry'].get('onTeamId')
                if not team_id:
                    continue
                player_name = player['playerPoolEntry']['player']['fullName']
                slot_id = player['lineupSlotId']
                for pos in player['playerPoolEntry']['player']['eligibleSlots']:
                    if pos in constants.POSITION_MAP:
                        position_id = pos
                        position = constants.POSITION_MAP[pos]

                for stat in player['playerPoolEntry']['player']['stats']:
                    # check if correct season, week and statSourceId are present in any of the player's dictionaries
                    # if not, get a replacement player
                    if not any(
                            all(
                                stat.get(key) == value
                                for key, value in {
                                    'seasonId': constants.SEASON,
                                    'scoringPeriodId': week,
                                    'statSourceId': 1
                                }.items()
                            )
                            for stat in player['playerPoolEntry']['player']['stats']
                    ):
                        position_id = -1
                        player_name = 'Free Agent'
                        projection = replacement_players[position]

                    else:
                        if stat['seasonId'] == constants.SEASON and stat['scoringPeriodId'] == week and stat['statSourceId'] == 1:
                            projection = stat['appliedTotal']

                if projection > 0:
                    roster_dict[player_id] = {
                        'week': week,
                        'team': team_name,
                        'player_id': player_id,
                        'player_name': player_name,
                        'slot_id': slot_id,
                        'position_id': position_id,
                        'position': position,
                        'projection': projection,
                        'played': 0
                    }

            # check if roster is full, if not fill with replacement player
            roster_non_ir = {k: v for k, v in roster_dict.items() if v['slot_id'] != 21}  # can't put IR player in lineup
            if len(roster_non_ir) < params.roster_size:
                for position in ['QB', 'RB', 'WR', 'TE', 'K']:
                    pos_dict = {k: v for k, v in roster_dict.items() if v['position'] == position}
                    pos_id = [k for k, v in rosters.slotcodes.items() if v == position][0]
                    limit = rosters.slot_limits.get(pos_id, 0)
                    if limit == 0:
                        continue

                    if len(pos_dict) < limit:
                        needed = limit - len(pos_dict)
                        for i in range(1, needed+1):
                            player_id = int(str(-1 * i) + str(pos_id))
                            roster_dict[player_id] = {
                                'week': week,
                                'team': team_name,
                                'player_id': player_id,
                                'player_name': 'Free Agent',
                                'slot_id': pos_id,
                                'position_id': pos_id,
                                'position': position,
                                'projection': replacement_players[position],
                                'played': 0
                            }

                flex_limit = rosters.slot_limits.get(23, 2)
                flex_eligible = {
                    k: v for k, v in roster_dict.items()
                    if v['position'] in ['RB', 'WR', 'TE']
                }
                required_flex_pool = (
                    rosters.slot_limits.get(2, 0)
                    + rosters.slot_limits.get(4, 0)
                    + rosters.slot_limits.get(6, 0)
                    + flex_limit
                )

                if len(flex_eligible) < required_flex_pool:
                    needed = required_flex_pool - len(flex_eligible)
                    best_flex_replacement = max(
                        ['RB', 'WR', 'TE'],
                        key=lambda p: replacement_players[p]
                    )
                    pos_id = [k for k, v in rosters.slotcodes.items() if v == best_flex_replacement][0]

                    for i in range(1, needed + 1):
                        player_id = int(str(-1 * i) + '23' + str(pos_id))
                        roster_dict[player_id] = {
                            'week': week,
                            'team': team_name,
                            'player_id': player_id,
                            'player_name': 'Free Agent',
                            'slot_id': 23,
                            'position_id': pos_id,
                            'position': best_flex_replacement,
                            'projection': replacement_players[best_flex_replacement],
                            'played': 0
                        }

            team_dict[team_name] = calculate_best_lineup(team_roster=roster_dict, rosters=rosters)
        projections_dict[week] = team_dict
    return projections_dict


def simulate_season(params: Params,
                    teams: Teams,
                    lineups: dict,
                    team_names: list[str] = None):
    """Simulate a full regular season"""
    all_weeks = []
    for week, team_lineups in lineups.items():
        if week <= params.regular_season_end:
            matchups = [m for m in teams.matchups['schedule'] if m['matchupPeriodId'] == week]
            matchup_sim = []
            scores = []
            for idx, m in enumerate(matchups):
                team1 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['away']['teamId'])
                if team_names and team1 not in team_names:
                    continue
                if team1 not in team_lineups:
                    continue
                lineup1 = team_lineups[team1]
                sim1 = simulate_lineup(lineup1)

                team2 = teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=m['home']['teamId'])
                if team_names and team2 not in team_names:
                    continue
                if team2 not in team_lineups:
                    continue
                lineup2 = team_lineups[team2]
                sim2 = simulate_lineup(lineup2)

                # redo sim if they are somehow tied
                if sim1 == sim2:
                    sim1 = simulate_lineup(lineup1)
                    sim2 = simulate_lineup(lineup2)
                scores.append(sim1)
                scores.append(sim2)

                matchup_sim.append({
                    'team': team1,
                    'score': sim1,
                    'matchup_result': 1 if sim1 > sim2 else 0
                })

                matchup_sim.append({
                    'team': team2,
                    'score': sim2,
                    'matchup_result': 1 if sim2 > sim1 else 0
                })
            for team_result in matchup_sim:
                if team_result['score'] > np.median(scores):
                    team_result['tophalf_result'] = 1
                elif team_result['score'] == np.median(scores):
                    team_result['tophalf_result'] = 0.5
                else:
                    team_result['tophalf_result'] = 0
                team_result['total_wins'] = team_result['matchup_result'] + team_result['tophalf_result']
            all_weeks.append(matchup_sim)

    season_sim_dict = {}
    for team in team_names:
        team_points = 0
        team_m_wins = 0
        team_th_wins = 0
        for week in all_weeks:
            team_data = [d for d in week if d['team'] == team]
            if not team_data:
                continue

            team_points += team_data[0]['score']
            team_m_wins += team_data[0]['matchup_result']
            team_th_wins += team_data[0]['tophalf_result']
        season_sim_dict[team] = {
            'matchup_wins': team_m_wins,
            'tophalf_wins': team_th_wins,
            'total_wins': team_m_wins,
            'total_points': team_points
        }

    return season_sim_dict


def get_playoff_teams(params: Params,
                      sim_data: dict):
    """Calculate playoff teams using division winners plus wild cards."""
    records = [
        {
            'team': team,
            'wins': values['matchup_wins'],
            'score': values['total_points']
        }
        for team, values in sim_data.items()
    ]

    return league_rules.playoff_team_names(
        records=records,
        playoff_teams=5
    )


def sim_playoff_round(week: int,
                      lineups: dict,
                      params: Params,
                      teams: Teams,
                      replacement_players: dict[float],
                      projections: list[dict] = None,
                      week_data: DataLoader = None,
                      rosters: Rosters = None,
                      n_bye: int = None,
                      round_teams: list[str] = None,
                      matchups: list[dict] = None):
    """Simulates one week of playoffs to determine which teams advance

    week: the week to simulate
    lineups: dictionary of all lineups that week
    rosters: rosters settings from ESPN API
    n_bye: number of teams with a BYE this round
    round_teams: list of teams in the current round

    returns: list of teams advancing to the next round
    """
    this_week_all_lineups = {w: l for w, l in lineups.items() if w == week}[week]
    this_round_lineups = {t: l for t, l in this_week_all_lineups.items() if t in round_teams}
    next_round_teams = []
    if n_bye:
        # add teams on bye to next round
        next_round_teams.extend(round_teams[0:n_bye])

    # simulate round with remaining teams
    this_round_teams = [t for t in round_teams if t not in next_round_teams]
    n_advance = int(len(this_round_teams) / 2)

    if week_data:
        # if in the playoffs, simulate current matchup
        results = simulate_matchup(week=week, week_data=week_data, rosters=rosters, params=params, replacement_players=replacement_players, matchups=matchups, projections=projections)
        winners = [teamid_to_name(ids=constants.TEAM_IDS, teams=teams, teamid=r['team']) for r in results if r['result']==1]
        next_round_teams.extend(winners)
        return next_round_teams
    else:
        this_round_scores = {}
        for team, lineup in {k: v for k, v in this_round_lineups.items() if k in this_round_teams}.items():
            for id, player in lineup.items():
                # get standard deviation for each player
                player['sd'] = player['projection'] * (0.2 if player['position'] == 'QB' else player['projection'] * 0.4)
            this_round_scores[team] = simulate_lineup(lineup=lineup)

        # top scoring teams advance to next round
        teams_sorted = dict(sorted(this_round_scores.items(), key=lambda item: item[1], reverse=True))
        next_round_teams.extend(list(teams_sorted.keys())[:n_advance])
        return next_round_teams
