import os
from dotenv import load_dotenv
import datetime as dt


load_dotenv()
DB_USER = os.getenv('DB_USER_LOCAL')
DB_PASS = os.getenv('DB_PASS_LOCAL')
DB_HOST = os.getenv('DB_HOST_LOCAL')
DB_NAME = os.getenv('DB_NAME_LOCAL')

# SSH DB credentials
DB_USER_SSH = os.getenv('DB_USER_SSH')
DB_PASS_SSH = os.getenv('DB_PASS_SSH')
DB_HOST_SSH = os.getenv('DB_HOST_SSH')  # SSH host
DB_NAME_SSH = os.getenv('DB_NAME_SSH')
# MySQL host for SSH tunnel (e.g., hgupta.mysql.pythonanywhere-services.com)
DB_MYSQL_HOST_SSH = os.getenv('DB_MYSQL_HOST_SSH')

CLINCHED = -99
ELIMINATED = 99
CLINCHED_DISP = 'c'
ELIMINATED_DISP = 'x'

N_SIMS = 100_000

# ESPN API parameters
_CURRENT_YEAR = dt.datetime.now().year
_CURRENT_MONTH = dt.datetime.now().month
# SEASON = _CURRENT_YEAR if _CURRENT_MONTH >= 9 else _CURRENT_YEAR-1
SEASON = 2025
LEAGUE_ID = os.getenv('LEAGUE_ID')
SWID = os.getenv('SWID')
ESPN_S2 = os.getenv('ESPN_S2')

# Database columns for inserts
MATCHUP_COLUMNS = 'id, season, week, team, score, opponent, opponent_score, matchup_result, tophalf_result'
POWER_RANK_COLUMNS = 'id, season, week, team, season_idx, week_idx, consistency_idx, manager_idx, luck_idx, power_score_raw, power_score_norm, power_rank, score_raw_change, score_norm_change, rank_change'
PROJECTIONS_COLUMNS = 'id, season, week, name, espn_id, position, receptions, projection'
H2H_COLUMNS = 'id, season, week, team, opponent, result'
EFFICIENCY_COLUMNS = 'id, season, week, team, actual_lineup_score, actual_lineup_projected, best_projected_lineup_score, best_projected_lineup_projected, optimal_lineup_score, optimal_lineup_projected'
SCHEDULE_SWITCH_COLUMNS = 'id, season, week, team, schedule_of, result'
WEEK_SIM_COLUMNS = 'id, season, week, matchup_id, team, avg_score, p_win, p_tophalf, p_highest, p_lowest'
SEASON_SIM_COLUMNS = 'id, season, week, team, matchup_wins, tophalf_wins, total_wins, total_points, playoffs, finals, champion'
RECORDS_COLUMNS = 'id, category, record, holder, season, week'
ALLTIME_STANDINGS_COLUMNS = 'id, team, seasons, playoffs, overall_rec, win_perc, matchup_rec, tophalf_rec, points'

STANDINGS_COLUMNS_FLASK = ['seed', 'team', 'overall', 'win_perc', 'matchup', 'top_half', 'total_points_disp', 'wb2_disp', 'wb5_disp', 'pb6_disp', 'bye_magic_number', 'playoff_magic_number']
RECORDS_COLUMNS_FLASK = ['category', 'record', 'holder', 'season', 'week']
ALLTIME_COLUMNS_FLASK = ['team', 'seasons', 'playoffs', 'overall_rec', 'win_perc', 'matchup_rec', 'tophalf_rec', 'points']


# Gamma distribution values for simulations
    # mean: average score of starters since 2021
    # a: alpha (shape)
    # loc: location
GAMMA_VALUES = {
    'QB': {
        'mean': 19.5,
        'a': 25.0963,
        'loc': -20.3195,
        'scale': 1.5820
    },
    'RB': {
        'mean': 13.5,
        'a': 2.9539,
        'loc': -0.2592,
        'scale': 4.6404
    },
    'WR': {
        'mean': 12.0,
        'a': 2.1777,
        'loc': 0.5273,
        'scale': 5.2803
    },
    'TE': {
        'mean': 9.5,
        'a': 1.7211,
        'loc': 0.8828,
        'scale': 4.9673
    },
    'DST': {
        'mean': 8.5,
        'a': 2.2054,
        'loc': 1.0673,
        'scale': 3.3139
    },
}

NFL_TEAM_MAP = {
    # NFL team ID to team abbreviation
    0:  'None',
    1:  'ATL',
    2:  'BUF',
    3:  'CHI',
    4:  'CIN',
    5:  'CLE',
    6:  'DAL',
    7:  'DEN',
    8:  'DET',
    9:  'GB',
    10: 'TEN',
    11: 'IND',
    12: 'KC',
    13: 'LV',
    14: 'LAR',
    15: 'MIA',
    16: 'MIN',
    17: 'NE',
    18: 'NO',
    19: 'NYG',
    20: 'NYJ',
    21: 'PHI',
    22: 'ARI',
    23: 'PIT',
    24: 'LAC',
    25: 'SF',
    26: 'SEA',
    27: 'TB',
    28: 'WSH',
    29: 'CAR',
    30: 'JAX',
    33: 'BAL',
    34: 'HOU'
}

POSITION_MAP = {
    # position ID to position name
    # only for NFL positions
    0:  'QB',
    2:  'RB',
    4:  'WR',
    6:  'TE',
    16: 'DST',
    17: 'K'
}

SLOTCODES = {
    # position ID to position
    # all fantasy positions
    0:  'QB',
    1:  'TQB',
    2:  'RB',
    3:  'Flex',  # RB/WR
    4:  'WR',
    5:  'Flex',  # WR/TE
    6:  'TE',
    7:  'OP',
    8:  'DT',
    9:  'DE',
    10: 'LB',
    11: 'DL',
    12: 'CB',
    13: 'S',
    14: 'DB',
    15: 'DP',
    16: 'DST',
    17: 'K',
    18: 'P',
    19: 'HC',
    20: 'BE',
    21: 'IR',
    22: '',
    23: 'Flex',  # RB/WR/TE
    24: 'ER',
    25: 'Rookie'
}

PLAYER_STATS_MAP = {
    # stat ID to stat name
    # Passing
    0: {'name': 'passingAttempts', 'display': 'Passing Attempts'},  # PA
    1: {'name': 'passingCompletions', 'display': 'Completions'},  # PC
    2: {'name': 'passingIncompletions', 'display': 'Incompletions'},  # INC
    3: {'name': 'passingYards', 'display': 'Passing Yards'},  # PY
    4: {'name': 'passingTouchdowns', 'display': 'Passing TDs'},  # PTD
    # 5-14 appear for passing players
    # 5-7: 6 is half of 5 (integer divide by 2), 7 is half of 6 (integer divide by 2)
    # 8-10: 9 is half of 8 (integer divide by 2), 10 is half of 9 (integer divide by 2)
    # 11-12: 12 is half of 11 (integer divide by 2)
    # 13-14: 14 is half of 13 (integer divide by 2)
    15: 'passing40PlusYardTD',  # PTD40
    16: 'passing50PlusYardTD',  # PTD50
    17: 'passing300To399YardGame',  # P300
    18: 'passing400PlusYardGame',  # P400
    19: 'passing2PtConversions',  # 2PC
    20: {'name': 'passingInterceptions', 'display': 'Passing INTs'},  # INT
    21: 'passingCompletionPercentage',
    22: 'passingYardsPerGame',  # PY - avg per game

    # Rushing
    23: {'name': 'rushingAttempts', 'display': 'Rushing Attempts'},  # RA
    24: {'name': 'rushingYards', 'display': 'Rushing Yards'},  # RY
    25: {'name': 'rushingTouchdowns', 'display': 'Rushing TDs'},  # RTD
    26: 'rushing2PtConversions',  # 2PR
    # 27-34 appear for rushing players
    # 27-29: 28 is half of 27 (integer divide by 2), 29 is half of 28 (integer divide by 2)
    # 30-32: 31 is half of 30 (integer divide by 2), 32 is half of 31 (integer divide by 2)
    # 33-34: 34 is half of 33 (integer divide by 2)
    35: 'rushing40PlusYardTD',  # RTD40
    36: 'rushing50PlusYardTD',  # RTD50
    37: 'rushing100To199YardGame',  # RY100
    38: 'rushing200PlusYardGame',  # RY200
    39: 'rushingYardsPerAttempt',
    40: 'rushingYardsPerGame',  # RY - avg per game

    # Receiving
    41: {'name': 'receivingReceptions', 'display': 'Receptions'},  # REC
    42: {'name': 'receivingYards', 'display': 'Receiving Yards'},  # REY
    43: {'name': 'receivingTouchdowns', 'display': 'Receiving TDs'},  # RETD
    44: 'receiving2PtConversions',  # 2PRE
    45: 'receiving40PlusYardTD',  # RETD40
    46: 'receiving50PlusYardTD',  # RETD50
    # 47-52 appear for receiving players
    # 47-49: 48 is half of 47 (integer divide by 2), 49 is half of 48 (integer divide by 2)
    # 50-52: 51 is half of 50 (integer divide by 2), 52 is half of 51 (integer divide by 2)
    53: {'name': 'receivingReceptions', 'display': 'Receptions'},  # REC - TODO: figure out what the difference is between 53 and 41
    # 54-55 appear for receiving players
    # 54-55: 55 is half of 54 (integer divide by 2)
    56: 'receiving100To199YardGame',  # REY100
    57: 'receiving200PlusYardGame',  # REY200
    58: {'name': 'receivingTargets', 'display': 'Targets'},  # RET
    59: 'receivingYardsAfterCatch',
    60: 'receivingYardsPerReception',
    61: 'receivingYardsPerGame',  # REY - avg per game
    62: '2PtConversions',
    63: 'fumbleRecoveredForTD',  # FTD
    64: 'passingTimesSacked',  # SK

    # Turnovers
    68: {'name': 'fumbles', 'display': 'Fumbles'},  # FUM
    72: {'name': 'lostFumbles', 'display': 'Fumbles Lost'},  # FUML
    73: 'turnovers',

    # Kicking
    74: 'madeFieldGoalsFrom50Plus',  # FG50 (does not map directly to FG50 as FG50 does not include 60+)
    75: 'attemptedFieldGoalsFrom50Plus',  # FGA50 (does not map directly to FGA50 as FG50 does not include 60+)
    76: 'missedFieldGoalsFrom50Plus',  # FGM50 (does not map directly to FGM50 as FG50 does not include 60+)
    77: 'madeFieldGoalsFrom40To49',  # FG40
    78: 'attemptedFieldGoalsFrom40To49',  # FGA40
    79: 'missedFieldGoalsFrom40To49',  # FGM40
    80: 'madeFieldGoalsFromUnder40',  # FG0
    81: 'attemptedFieldGoalsFromUnder40',  # FGA0
    82: 'missedFieldGoalsFromUnder40',  # FGM0
    83: 'madeFieldGoals',  # FG
    84: 'attemptedFieldGoals',  # FGA
    85: 'missedFieldGoals',  # FGM
    86: 'madeExtraPoints',  # PAT
    87: 'attemptedExtraPoints',  # PATA
    88: 'missedExtraPoints',  # PATM

    # Defense
    89: 'defensive0PointsAllowed',  # PA0
    90: 'defensive1To6PointsAllowed',  # PA1
    91: 'defensive7To13PointsAllowed',  # PA7
    92: 'defensive14To17PointsAllowed',  # PA14
    93: 'defensiveBlockedKickForTouchdowns',  # BLKKRTD
    94: 'defensiveTouchdowns',  # Does not include defensive blocked kick for touchdowns (BLKKRTD)
    95: 'defensiveInterceptions',  # INT
    96: 'defensiveFumbles',  # FR
    97: 'defensiveBlockedKicks',  # BLKK
    98: 'defensiveSafeties',  # SF
    99: 'defensiveSacks',  # SK
    # 100: This appears to be defensiveSacks * 2
    101: 'kickoffReturnTouchdowns',  # KRTD
    102: 'puntReturnTouchdowns',  # PRTD
    103: 'interceptionReturnTouchdowns',  # INTTD
    104: 'fumbleReturnTouchdowns',  # FRTD
    105: 'DSTTouchdowns',  # Includes defensive blocked kick for touchdowns (BLKKRTD) and kickoff/punt return touchdowns
    106: 'defensiveForcedFumbles',  # FF
    107: 'defensiveAssistedTackles',  # TKA
    108: 'defensiveSoloTackles',  # TKS
    109: 'defensiveTotalTackles',  # TK
    113: 'defensivePassesDefensed',  # PD

    # Kick/Punt Returns
    114: 'kickoffReturnYards',  # KR
    115: 'puntReturnYards',  # PR
    118: 'puntsReturned',  # PTR

    # Team Defense Points Allowed
    120: 'defensivePointsAllowed',  # PA
    121: 'defensive18To21PointsAllowed',  # PA18
    122: 'defensive22To27PointsAllowed',  # PA22
    123: 'defensive28To34PointsAllowed',  # PA28
    124: 'defensive35To45PointsAllowed',  # PA35
    125: 'defensive45PlusPointsAllowed',  # PA46

    # Team Defense Yards Allowed
    127: 'defensiveYardsAllowed',  # YA
    128: 'defensiveLessThan100YardsAllowed',  # YA100
    129: 'defensive100To199YardsAllowed',  # YA199
    130: 'defensive200To299YardsAllowed',  # YA299
    131: 'defensive300To349YardsAllowed',  # YA349
    132: 'defensive350To399YardsAllowed',  # YA399
    133: 'defensive400To449YardsAllowed',  # YA449
    134: 'defensive450To499YardsAllowed',  # YA499
    135: 'defensive500To549YardsAllowed',  # YA549
    136: 'defensive550PlusYardsAllowed',  # YA550

    # Punting
    138: 'netPunts',  # PT
    139: 'puntYards',  # PTY
    140: 'puntsInsideThe10',  # PT10
    141: 'puntsInsideThe20',  # PT20
    142: 'blockedPunts',  # PTB
    145: 'puntTouchbacks',  # PTTB
    146: 'puntFairCatches',  # PTFC
    147: 'puntAverage',
    148: 'puntAverage44.0+',  # PTA44
    149: 'puntAverage42.0-43.9',  # PTA42
    150: 'puntAverage40.0-41.9',  # PTA40
    151: 'puntAverage38.0-39.9',  # PTA38
    152: 'puntAverage36.0-37.9',  # PTA36
    153: 'puntAverage34.0-35.9',  # PTA34
    154: 'puntAverage33.9AndUnder',  # PTA33

    # Head Coach
    155: 'teamWin',  # TW
    156: 'teamLoss',  # TL
    157: 'teamTie',  # TIE
    158: 'pointsScored',  # PTS
    160: 'pointsMargin',
    161: '25+pointWinMargin',  # WM25
    162: '20-24pointWinMargin',  # WM20
    163: '15-19pointWinMargin',  # WM15
    164: '10-14pointWinMargin',  # WM10
    165: '5-9pointWinMargin',  # WM5
    166: '1-4pointWinMargin',  # WM1
    167: '1-4pointLossMargin',  # LM1
    168: '5-9pointLossMargin',  # LM5
    169: '10-14pointLossMargin',  # LM10
    170: '15-19pointLossMargin',  # LM15
    171: '20-24pointLossMargin',  # LM20
    172: '25+pointLossMargin',  # LM25
    174: 'winPercentage',  # Value goes from 0-1

    187: 'defensivePointsAllowed',  # TODO: figure out what the difference is between 187 and 120

    # Field Goal extra
    201: 'madeFieldGoalsFrom60Plus',  # FG60
    202: 'attemptedFieldGoalsFrom60Plus',  # FGA60
    203: 'missedFieldGoalsFrom60Plus',  # FGM60

    205: 'defensive2PtReturns',  # 2PTRET
    206: 'defensive2PtReturns'  # 2PTRET - TODO: figure out what the difference is between 206 and 205
}

TEAM_IDS = {
    # add new teams here
    '{000ADC3F-14C0-418C-83B4-56B1D0919383}': {
        'active': True,
        'name': {
            'first': 'Caden',
            'last': 'Bucknerrrrr',
            'display': 'Gustavo'
        }
    },
    '{089801F7-BA02-427B-9801-F7BA02B27B96}': {
        'active': True,
        'name': {
            'first': 'Tripp',
            'last': 'Winniford',
            'display': 'Riceism'
        }
    },
    '{0D5E54B1-D7A2-4E3C-9E54-B1D7A26E3C78}': {
        'active': True,
        'name': {
            'first': 'Jordan',
            'last': 'Yoder',
            'display': 'The Warriors'
        }
    },
    '{2B5B6A25-C8B8-45EB-9B6A-25C8B805EBAA}': {
        'active': True,
        'name': {
            'first': 'Chase',
            'last': 'Yoder',
            'display': 'Moose Knuckle'
        }
    },
    '{3E97B7E5-216F-42BC-9E34-E3DC4E002930}': {
        'active': True,
        'name': {
            'first': 'Luke',
            'last': 'Burnette',
            'display': 'Mighty Acorns'
        }
    },
    '{44E97B48-5469-4DA7-BA73-C431934CEB35}': {
        'active': True,
        'name': {
            'first': 'thomas',
            'last': 'mccartney',
            'display': 'Grudens Grinders'
        }
    },
    '{81B6CF9E-2070-4C7D-A481-4399C5DFD344}': {
        'active': True,
        'name': {
            'first': 'Cade',
            'last': 'Smitherman',
            'display': 'Bijario'
        }
    },
    '{D62C1EF4-D8C6-4017-AC1E-F4D8C650177B}': {
        'active': True,
        'name': {
            'first': 'Landry',
            'last': 'Droupy',
            'display': 'droupymagic'
        }
    },
    '{E6F4927B-0C19-425F-B492-7B0C19025FF4}': {
        'active': True,
        'name': {
            'first': 'Quinn',
            'last': 'McDermott',
            'display': 'Riceism'
        }
    },
    '{FE034A7C-E6FD-4520-BB85-BA598ECB2746}': {
        'active': True,
        'name': {
            'first': 'Leighton',
            'last': 'Archer',
            'display': 'Kitty\'s Revenge'
        }
    
    },
    '{552ABD2B-331C-46EF-AABD-2B331C06EF2D}': 
    {
        'active': False,
        'name': {
            'first': 'Chase',
            'last': 'Yoder',
            'display': 'Harpers Booty'  # or correct team name
        }
    },
    '{C0284191-8F36-4640-BBA9-11596348CD1A}': 
    {
        'active': False,
        'name': {
            'first': 'Peyton',
            'last': 'Yoder',
            'display': '24th Nut'  # or correct team name
        }
    }
    
    
}
