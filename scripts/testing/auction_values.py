import os
from datetime import datetime
import pandas as pd
import numpy as np
import random
import pulp
from time import time
from functools import reduce
import warnings
from sklearn.mixture import GaussianMixture as gm
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.colors as colors
import scipy.stats as stats
import nfl_data_py as nfl
import requests
warnings.simplefilter(action='ignore')

# parameters
TEAMS = 10
POSITIONS = ["QB", "RB", "WR", "TE", "DST"]  # draftable positions
STARTERS = [1, 2, 3, 1, 1]  # number of starters by position
BENCH = 6
BACKUPS = [0.5/BENCH, 2.5/BENCH, 2.5/BENCH, 0.5/BENCH, 0]  # percent of bench spots occupied by position
N_FLEX = 1  # number of flexes
FLEX_POSITIONS = ["RB", "WR"]  # TEs are typically not played in flex
BUDGET = 200
MIN_BID = 1
STARTER_ALLOC = 0.8  # percent of available budget allocated to starters

# map team to abbreviation
def_mapping = {'Arizona Cardinals':'ARI', 'Atlanta Falcons':'ATL', 'Baltimore Ravens':'BAL',
               'Buffalo Bills':'BUF', 'Carolina Panthers':'CAR', 'Chicago Bears':'CHI',
               'Cincinnati Bengals':'CIN', 'Cleveland Browns':'CLE', 'Dallas Cowboys':'DAL',
               'Denver Broncos':'DEN', 'Detroit Lions':'DET', 'Green Bay Packers':'GB',
               'Houston Texans':'HOU', 'Indianapolis Colts':'IND', 'Jacksonville Jaguars':'JAC',
               'Kansas City Chiefs':'KC', 'Las Vegas Raiders':'LV', 'Los Angeles Chargers':'LAC',
               'Los Angeles Rams':'LAR', 'Miami Dolphins':'MIA', 'Minnesota Vikings':'MIN',
               'New England Patriots':'NE', 'New Orleans Saints':'NO', 'New York Giants':'NYG',
               'New York Jets':'NYJ', 'Philadelphia Eagles':'PHI', 'Pittsburgh Steelers':'PIT',
               'San Francisco 49ers':'SF', 'Seattle Seahawks':'SEA', 'Tampa Bay Buccaneers':'TB',
               'Tennessee Titans':'TEN', 'Washington Commanders':'WAS'}


def load_fantasy_data(positions):
    positions = POSITIONS
    all_players = pd.DataFrame()
    for pos in positions:
        # load player projections by positino from fantasy pros
        pos_lower = pos.lower()
        url = f"https://www.fantasypros.com/nfl/projections/{pos_lower}.php?week=draft&scoring=HALF&week=draft"
        pos_df = pd.read_html(url)[0]

        # fix column names -- dst is different
        if pos != "DST":
            pos_df.columns = ["player"] + ['_'.join(col).strip().lower() for col in pos_df.columns.values[1:]]
            pos_df["team"] = pos_df.player.str[-3:].str.strip()
            pos_df["player"] = pos_df.player.str[:-3].str.strip()
        else:
            pos_df.columns = [col.lower().replace(" ", "_") for col in pos_df.columns[:-1]] + ["misc_fpts"]
            pos_df["team"] = pos_df.player.map(def_mapping)

        pos_df["position"] = pos
        pos_df["pos_rank"] = pos_df.index.values + 1

        all_players = pd.concat([all_players, pos_df])
        all_players["id"] = all_players.reset_index(drop=True).index + 1000

    return all_players[["id", "player", "position", "team", "pos_rank", "misc_fpts"]].fillna(0)


def calculate_prices(players_data, type, p=POSITIONS, s=STARTERS, b=BACKUPS):
    bench_allocation = round(1 - STARTER_ALLOC, 2)  # percent of budget allocated to bench
    total_dollars = BUDGET * TEAMS
    roster_size = sum(STARTERS) + BENCH + N_FLEX
    available_spend = (total_dollars - (roster_size * MIN_BID * TEAMS))  # each player costs a min of $1 leaving ($200 - roster_size) to spend per team

    if type == 'current':
        cols_to_keep = ["id", "player", "position", "team", "pos_rank", "misc_fpts", "vor_st", "vor_bn", "vor_tot", "type"]
        final_cols = ["id", "player", "position", "team", "ovr_rank", "pos_rank", "misc_fpts", "ppg", "vor_tot", "type", "value", "price"]
    elif type == 'last_yr':
        cols_to_keep = ["player", "season", "position", "pos_rank", "misc_fpts", "games", "vor_st", "vor_bn", "vor_tot", "type"]
        final_cols = ["player", "season", "position", "ovr_rank", "pos_rank", "misc_fpts", "ppg", "vor_tot", "type", "value", "price"]

    undrafted = pd.DataFrame()
    drafted = pd.DataFrame()
    for pos in zip(p, s, b):
        pos_df = players_data[players_data.position == pos[0]]
        if pos[0] in FLEX_POSITIONS:
            n_total_drafted = ((pos[1] + (N_FLEX / len(FLEX_POSITIONS))) * TEAMS)\
                              + (BENCH * pos[2] * TEAMS)  # drafted starters + bench
            n_starters_drafted = (pos[1] + 0.5) * TEAMS
            repl_rank_starters = n_starters_drafted + 1
        else:
            n_total_drafted = (pos[1] * TEAMS) + (BENCH * pos[2] * TEAMS)
            repl_rank_starters = pos[1] * TEAMS + 1

        repl_rank_bench = np.floor(n_total_drafted + 1)
        repl_rank_starters_fpts = pos_df[pos_df.pos_rank == repl_rank_starters]["misc_fpts"].values[0]
        repl_rank_bench_fpts = pos_df[pos_df.pos_rank == repl_rank_bench]["misc_fpts"].values[0]
        pos_df["type"] = np.where(pos_df.pos_rank < repl_rank_starters, "starter",
                                  np.where(pos_df.pos_rank < repl_rank_bench, "bench",
                                           "undrafted"))
        pos_df["vor_st"] = np.where(pos_df.misc_fpts - repl_rank_starters_fpts > 0,
                                    pos_df.misc_fpts - repl_rank_starters_fpts, 0)
        pos_df["vor_bn"] = pos_df.misc_fpts - repl_rank_bench_fpts - pos_df.vor_st
        pos_df["vor_tot"] = round(pos_df.vor_st + pos_df.vor_bn, 4)

        # separate undrafted players
        pos_undrafted = pos_df[pos_df.type == "undrafted"][cols_to_keep]
        undrafted = pd.concat([undrafted, pos_undrafted]).sort_values(["vor_tot", "misc_fpts"], ascending=False)
        # undrafted["vor_tot"] = 1
        undrafted["price"] = 0
        undrafted["value"] = 1

        # calculate price for drafted players
        pos_drafted = pos_df[pos_df.type != "undrafted"][cols_to_keep]
        drafted = pd.concat([drafted, pos_drafted]).sort_values(["vor_tot", "misc_fpts"], ascending=False)

    starter_dol_per_vor = ((available_spend * STARTER_ALLOC) / drafted[drafted.type == "starter"].vor_st.sum())\
                          + ((available_spend * bench_allocation) / drafted[drafted.type == "starter"].vor_bn.sum())
    bench_dol_per_vor = (available_spend * bench_allocation) / drafted[drafted.type == "bench"].vor_tot.sum()

    drafted["value"] = (drafted.vor_st * starter_dol_per_vor) \
                       + (drafted.vor_bn * bench_dol_per_vor) \
                       + MIN_BID
    drafted["value"] = np.where(drafted.position == "DST", drafted.value/2, drafted.value)  # adjust dst price down
    drafted = drafted.reset_index(drop=True)

    # adjust final price for drafted players to equal total available funds
    drafted["price"] = drafted.value / (drafted[drafted.type != "undrafted"].value.sum() / total_dollars)

    # combine drafted and undrafted players
    all_players = pd.concat([drafted, undrafted]).reset_index(drop=True)
    all_players["ovr_rank"] = all_players[["price", "vor_tot"]].apply(tuple, axis=1).rank(method="first", ascending=False).astype(int)
    all_players = all_players.sort_values(["ovr_rank"])
    all_players["price"] = np.where(all_players.price < 1, 1, all_players.price.round())

    if type == 'current':
        all_players["ppg"] = round(all_players.misc_fpts / 17, 2)
    else:
        all_players["ppg"] = round(all_players.misc_fpts / all_players.games, 2)

    return all_players[final_cols].reset_index(drop=True)


def build_team(player_ids:list, data):
    roster_spots = sum(STARTERS) + N_FLEX + BENCH
    n_starters = sum(STARTERS) + N_FLEX
    drafted = data[data.id.isin(player_ids)]
    drafted["ppg"] = round(drafted.misc_fpts / 17, 2)
    avail_spend = BUDGET * STARTER_ALLOC

    # check if number of roster spots met
    if len(player_ids) != n_starters:
        raise ValueError(f"Wrong number of players supplied. {len(player_ids)} submitted, need {roster_spots}")

    # check if number of starters met
    for pos in zip(POSITIONS, STARTERS):
        if len(drafted[drafted.position == pos[0]]) < pos[1]:
            raise ValueError(f"Not enough {pos[0]} starters. {len(drafted[drafted.position == pos[0]])} submitted, need {pos[1]}")

    # check if flex met
    if len(drafted[drafted.position == FLEX_POSITIONS[0]]) <= STARTERS[1]\
            and len(drafted[drafted.position == FLEX_POSITIONS[1]]) <= STARTERS[2]:
        raise ValueError(f"Need a flex player. Add a {FLEX_POSITIONS[0]} or {FLEX_POSITIONS[1]}")

    # check if team costs more than budget
    if drafted.price.sum() > avail_spend:
        raise ValueError(f"Team costs more than {avail_spend} by {drafted.price.sum() - avail_spend}\n{drafted[['id', 'player', 'price']]}")

    return {"total_points": round(drafted.misc_fpts.sum(), 2),
            "ppg": round(drafted.misc_fpts.sum() / 17, 2),
            "total_spend": drafted.price.sum(),
            "funds_remaining": avail_spend - drafted.price.sum(),
            "total_value": round(drafted.vor_tot.sum(), 2),
            "team": drafted[["id", "player", "position", "misc_fpts", "ppg", "vor_tot", "price"]]}


def optimize(data, reward: str, cost: str, cap=185):
    data.loc[(data.position == 'RB') & (data.pos_rank.isin([i for i in range(25, 35)])), 'position'] = "FLEX"
    data.loc[(data.position == 'WR') & (data.pos_rank.isin([i for i in range(37, 47)])), 'position'] = "FLEX"
    data["player_lookup"] = data.position + "_" + data.player.replace(r"\s", "_", regex=True)
    pos_num_available = {
        "QB": 1,
        "RB": 2,
        "WR": 3,
        "TE": 1,
        "FLEX": 1,
        "DST": 1
    }

    prices = {}
    points = {}
    for pos in POSITIONS + ["FLEX"]:
        available_pos = data[data.position == pos]
        price = list(available_pos[["player", cost]].set_index("player").to_dict().values())[0]
        point = list(available_pos[["player", reward]].set_index("player").to_dict().values())[0]
        prices[pos] = price
        points[pos] = point

    _vars = {position: pulp.LpVariable.dict(position, player_dict, cat="Binary") for position, player_dict in points.items()}

    # set up the optimization
    # prob: the function?
    # rewards: what we are maximizing (ppg)
    # costs:  what we're constrained by (player price)
    prob = pulp.LpProblem("Fantasy", pulp.LpMaximize)
    rewards = []
    costs = []

    # Setting up the reward
    for position, player_dict in _vars.items():
        costs += pulp.lpSum([prices[position][player] * _vars[position][player] for player in player_dict])
        rewards += pulp.lpSum([points[position][player] * _vars[position][player] for player in player_dict])
        prob += pulp.lpSum([_vars[position][player] for player in player_dict]) <= pos_num_available[position]

    prob += pulp.lpSum(rewards)
    prob += pulp.lpSum(costs) <= cap

    prob.solve()

    # get selected players
    cols = ["player", "position", "ovr_rank", "pos_rank", "ppg", "vor_tot", "value", "price"]
    players_included = pd.DataFrame()
    for player in prob.variables():
        if player.varValue == 1:
            player_data = data[data.player_lookup == player.name][cols]
            players_included = pd.concat([players_included, player_data])

    print(f"Total {reward}: {round(players_included[reward].sum(), 2)}")

    return players_included


players_data = load_fantasy_data(positions=POSITIONS)
# players_data = pd.read_csv(r'./Outputs/players_data_2022.csv')
auction_data = calculate_prices(players_data, 'current', POSITIONS, STARTERS, BACKUPS)
# auction_data = pd.read_csv(r'./Outputs/auction_data.csv')

# prior preseason auction data
auction_data_ly = pd.DataFrame()
for f in [f for f in os.listdir('Outputs') if f.startswith('players_data')]:
    temp = pd.read_csv(fr'Outputs/{f}')
    temp['pos_rank'] = temp\
        .groupby(['season', 'position'])\
        .misc_fpts.rank(method='dense', ascending=False)
    auction_temp = calculate_prices(players_data=temp, type='last_yr')
    auction_temp['player'] = auction_temp.player.str.replace('.', '')
    auction_temp['player'] = auction_temp.player.str.replace(' Jr', '')
    auction_temp['player'] = auction_temp.player.str.replace(' Sr', '')
    auction_temp['player'] = auction_temp.player.str.replace(' III', '')
    auction_temp['player'] = auction_temp.player.str.replace(' II', '')
    auction_data_ly = pd.concat([auction_data_ly, auction_temp])


def load_py_actuals(seasons:list):
    player_ids = nfl.import_players()[['gsis_id', 'display_name']]
    act_data = pd.merge(nfl.import_weekly_data(seasons), player_ids, left_on='player_id', right_on='gsis_id')
    act_data = act_data[act_data.position.isin(['QB', 'RB', 'WR', 'TE'])]
    act_data['misc_fpts'] = act_data.fantasy_points + (0.5 * act_data.receptions)
    act_data = act_data\
        .groupby(['player_id', 'display_name', 'position_group', 'season'])\
        .agg({'misc_fpts': 'sum', 'week': 'count'})\
        .reset_index()\
        .drop('player_id', axis=1)\
        .rename(columns={'display_name': 'player', 'position_group': 'position', 'week': 'games'})
    act_data['pos_rank'] = act_data.groupby(['season', 'position']).misc_fpts.rank(method='dense', ascending=False)
    auction_data_act = pd.DataFrame()
    for s in seasons:
        temp = act_data[act_data.season == s]
        auction_act_temp = calculate_prices(players_data=temp,
                                            type='last_yr',
                                            p=['QB', 'RB', 'WR', 'TE'],
                                            s=[1, 2, 3, 1],
                                            b=[0.5/BENCH, 2.5/BENCH, 2.5/BENCH, 0.5/BENCH])
        auction_act_temp['player'] = auction_act_temp.player.str.replace('.', '')
        auction_act_temp['player'] = auction_act_temp.player.str.replace(' Jr', '')
        auction_act_temp['player'] = auction_act_temp.player.str.replace(' Sr', '')
        auction_act_temp['player'] = auction_act_temp.player.str.replace(' III', '')
        auction_act_temp['player'] = auction_act_temp.player.str.replace(' II', '')
        auction_data_act = pd.concat([auction_data_act, auction_act_temp])

    return act_data, auction_data_act


py_act = load_py_actuals(seasons=[2022, 2023])
act_data = py_act[0]
auction_data_act = py_act[1]


final_auction_ly = pd.merge(auction_data_ly, auction_data_act, on=['player', 'season', 'position'], suffixes=['_proj', '_act'])
auction_ly_diff = auction_data_act.set_index(['player', 'season', 'position']).drop('type', axis=1) - auction_data_ly.set_index(['player', 'season', 'position']).drop('type', axis=1)
auction_ly_diff = auction_ly_diff[~auction_ly_diff.price.isnull()].reset_index().sort_values('value', ascending=False)

act_data = act_data[act_data.position.isin(['QB', 'RB', 'WR', 'TE'])]
stdev_mean = act_data.groupby(['season', 'player', 'position']).misc_fpts.mean().reset_index()
stdev_std = act_data.groupby(['season', 'player', 'position']).misc_fpts.std().reset_index()
stdevs = pd.merge(stdev_mean, stdev_std, on=['season', 'player', 'position'], suffixes=['_mean', '_std'])
stdevs = stdevs[(stdevs.misc_fpts_mean >= 5) & ~(stdevs.misc_fpts_std.isnull())]
stdevs = stdevs.head(100)
stdevs.groupby('position').agg({'misc_fpts_mean': ['mean', 'std']})
stdevs['std_perc'] = stdevs.misc_fpts_std / stdevs.misc_fpts_mean
stdevs.groupby('position').std_perc.plot.kde(legend=True)
stdevs.groupby('position').std_perc.mean()

# create clusters
data = auction_data.head(200)
values = data[['value']]

# gaussian mixture
gmcl = gm(n_components=10, covariance_type='full').fit(values)
gmcl.bic(values)
data['tier'] = gmcl.predict(values)



# players = [1010, 1088, 1107, 1267, 1276, 1274, 1106, 1520, 1662]
# build_team(player_ids=players, data=auction_data)

# opt_ppg = optimize(auction_data, "ppg", "price")
# opt_val = optimize(auction_data, "value", "price")
# opt_vor = optimize(auction_data, "vor_tot", "price")


def flatten(lst):
    rt = []
    for i in lst:
        if isinstance(i, list):
            rt.extend(flatten(i))
        else:
            rt.append(i)
    return rt


# auction draft simulation
def nominate_player(df, teams_df, draftable_players):
    # get positions available to draft
    teams = teams_df.copy()
    avail_pos = teams[teams.player.isnull()].slot.drop_duplicates().to_list()
    replace_bench = [i.replace('BENCH', 'QB, RB, WR, TE') for i in avail_pos]
    replace_bench = [i.split(', ') for i in replace_bench]
    avail_pos_final = list(set(flatten(replace_bench)))

    df = draftable_players.copy()
    df = df[df.position.isin(avail_pos_final)]
    df = df.head(10)
    players = df.player.to_list()
    selection_probabilities = list(df.value / (df.value).sum())

    return np.random.choice(players, 1, selection_probabilities)[0]


def winning_team(owners, teams_df, nominated_player_pos, init_bid, available_budgets, max_slots):
    def possible_teams(bid):
        df = teams_df.copy()
        df['filled'] = np.where(df.player.isnull(), 0, 1)
        max_pos = [max_slots[k] for k in max_slots if nominated_player_pos in k][0]
        if nominated_player_pos in FLEX_POSITIONS:
            # RBs and WRs can take up a flex spot
            avail_slots = [nominated_player_pos, 'FLEX', 'BENCH']
        else:
            # all other positions cannot
            avail_slots = [nominated_player_pos, 'BENCH']

        df = df[df.slot.isin(avail_slots)]  # first filter for slots position can occupy

        # filter out people that have met position limit
        can_draft = []
        for tm in df.team.drop_duplicates().to_list():
            df_tm = df[df.team == tm]
            if len(df_tm[df_tm.position == nominated_player_pos].groupby('team').filled.sum()) == 0:
                can_draft.append(tm)
            elif df_tm[df_tm.position == nominated_player_pos].filled.sum() < max_pos:
                can_draft.append(tm)
            else:
                pass

        df = df[df.team.isin(can_draft)]  # filter for teams that have not met position limit

        # remove teams that would fall below $1/remaining slot
        cannot_draft = []
        for o in owners:
            if (available_budgets[o]['funds_left'] - init_bid) / available_budgets[o]['slots_left'] < 1:
                cannot_draft.append(o)
        df = df[~df.team.isin(cannot_draft)]
        df = df[df.player.isnull()]  # get empty slots

        return df.team.drop_duplicates().to_list(), df

    poss_teams = []
    while (len(poss_teams) == 0) & (init_bid > 0):
        poss_teams.extend(possible_teams(init_bid)[0])

        if len(poss_teams) > 0:
            bid_final = init_bid
            break

        if len(poss_teams) == 0:
            init_bid -= 1

            if init_bid < 1:
                raise ValueError("No team able to draft player")
            else:
                continue

    if bid_final < 1:
        bid_final = 1

    the_team = np.random.choice(poss_teams, 1)[0]
    final_df = possible_teams(bid_final)[1]

    return final_df[final_df.team == the_team].head(1), bid_final


def inflation(remaining_prices: list, total_spent):
    return ((BUDGET * TEAMS) - total_spent) / sum(remaining_prices)


def sim_auction(n_sim=1):
    sim = 1
    times = []
    owners = ['aaron', 'aditya', 'akshat', 'arjun', 'ayaz', 'charles',
              'faizan', 'hirsh', 'harsh', 'nick', 'sharan', 'vikram']
    team_positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'WR', 'TE', 'FLEX', 'DST',
                      'BENCH', 'BENCH', 'BENCH', 'BENCH', 'BENCH', 'BENCH']
    total_slots = (TEAMS * (sum(STARTERS) + N_FLEX + BENCH))
    max_slots = {
        'QB': 2,
        'RB': 7,
        'WR': 8,
        'TE': 2,
        'DST': 1
    }  # realistic max slots, not ESPN max

    # need to have (max_slots * n_teams) players available per position
    # i.e 2 * 12 = 24 QBs available to draft
    qb_filt = (auction_data.position == 'QB') & (auction_data.pos_rank <= max_slots['QB'] * TEAMS)
    rb_filt = (auction_data.position == 'RB') & (auction_data.pos_rank <= max_slots['RB'] * TEAMS)
    wr_filt = (auction_data.position == 'WR') & (auction_data.pos_rank <= max_slots['WR'] * TEAMS)
    te_filt = (auction_data.position == 'TE') & (auction_data.pos_rank <= max_slots['TE'] * TEAMS)
    dst_filt = (auction_data.position == 'DST') & (auction_data.pos_rank <= max_slots['DST'] * TEAMS)
    draftable = auction_data[qb_filt | rb_filt | wr_filt | te_filt | dst_filt]

    all_sims = pd.DataFrame()
    while n_sim >= sim:
        start = time()
        # initiate dataframe of teams

        teams_df = pd.DataFrame(columns=['team', 'slot', 'player', 'position', 'bid', 'pick'])
        teams_df['team'] = np.repeat(owners, (sum(STARTERS) + N_FLEX + BENCH))
        teams_df['slot'] = team_positions * TEAMS
        teams_df['bid'] = teams_df.bid.fillna(0)

        available_budgets = {o: {
            'funds_left': BUDGET + 1,
            'slots_left': (sum(STARTERS) + N_FLEX + BENCH)
        } for o in owners}

        draftable_players = draftable.copy()

        players_drafted = []
        bids = []
        while len(players_drafted) < total_slots:
            try:
                # get nominated player
                nominated_player = nominate_player(draftable_players, teams_df, draftable_players)
                nominated_player_pos = draftable_players[draftable_players.player == nominated_player].position.values[0]

                # get winning bid and team
                min_bid = round(draftable_players[draftable_players.player == nominated_player].price.values[0])
                max_bid = round(draftable_players[draftable_players.player == nominated_player].value.values[0])
                init_bid = np.ceil(random.uniform(min_bid, max_bid))

                the_team = winning_team(owners, teams_df, nominated_player_pos, init_bid, available_budgets, max_slots)

                team = the_team[0]
                winning_bid = the_team[1]
                bids.append(winning_bid)

                # update tables
                players_drafted.append(nominated_player)
                draftable_players = draftable_players[~draftable_players.player.isin(players_drafted)]
                infl = inflation(draftable_players.price.to_list(), sum(bids))
                draftable_players[["value", "price"]] = draftable_players[["value", "price"]] * infl

                # get winning team
                teams_df.iloc[team.index[0], [2, 3, 4]] = [nominated_player, nominated_player_pos, winning_bid]
                teams_df.iloc[team.index[0], 5] = len(players_drafted)

                available_budgets[team.team.values[0]]['funds_left'] -= winning_bid  # adjust budget, add 1 to account for players needed
                available_budgets[team.team.values[0]]['slots_left'] -= 1  # player drafted
                print(f"{len(players_drafted)}/{total_slots} | {nominated_player} drafted by {team.team.values[0]} for ${int(winning_bid)}")

                if len(players_drafted) == 50:
                    break
            except ValueError:
                draftable_players = draftable_players[~draftable_players.player.isin([nominated_player])]
                continue

            teams_df['sim'] = sim

        end = time()
        all_sims = pd.concat([all_sims, teams_df])
        elapsed = round(end - start, 1)
        times.insert(len(times) + 1, elapsed)
        print(f"Sim #{sim}: {elapsed} seconds")
        sim += 1

    return all_sims, times


sims = pd.read_csv(r'./Outputs/2024/auction_sims_2024-08-18.csv')
sim_times = pd.read_csv(r'./Outputs/2024/auction_sim_times_2024-08-18.csv')
sim_times['rolling_average'] = sim_times.sim_times.rolling(50).mean()

plt.figure(figsize=(7, 7))
plt.axhline(y=sim_times.sim_times.mean(), c='grey', dashes=(2, 2, 2, 2))
plt.plot(sim_times.index, sim_times.rolling_average)
plt.xlabel('Sim Number')
plt.ylabel('Time (min)')
plt.show()

sims = pd.merge(sims, auction_data.drop(['id', 'team', 'position', 'type'], axis=1), on='player', how='left')


def scatter_plot(player, x='pick', y='bid'):
    df = sims.copy()
    df_plyr = df[df.player == player]
    plt.figure(figsize=(7, 7))
    plt.axvline(x=df_plyr[x].mean(), c='grey', dashes=(2, 2, 2, 2))
    plt.axhline(y=df_plyr[y].median(), c='grey', dashes=(2, 2, 2, 2))
    plt.scatter(df_plyr[x], df_plyr[y], s=5)
    plt.title(player)
    plt.xlabel(x)
    plt.ylabel(y)
    plt.show()


scatter_plot(player='Kyler Murray')

benches = sims[sims.slot == 'BENCH'].sort_values('bid', ascending=False)
bench_bids = sims[sims.slot == 'BENCH'].groupby(['sim', 'team']).bid.sum().reset_index()
bench_bids['p_bench'] = bench_bids.bid / 200


avg_prices = sims.groupby('player').agg({'bid': 'mean'}).reset_index()
std_prices = sims.groupby('player').agg({'bid': 'std'}).reset_index()
prices = pd.merge(avg_prices, std_prices, on='player').rename(columns={'bid_x':'mean', 'bid_y':'std'}).sort_values('mean', ascending=False)


def get_byes(season):
    season = 2024
    url = f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}?view=proTeamSchedules_wl'
    r = requests.get(url)
    d = r.json()

    byes_dict = {}
    for tm in d['settings']['proTeams']:
        byes_dict[tm['abbrev'].upper()] = tm['byeWeek']

    # get team  bye weeks
    # tm_map = pd.read_csv("https://gist.githubusercontent.com/cnizzardini/13d0a072adb35a0d5817/raw/dbda01dcd8c86101e68cbc9fbe05e0aa6ca0305b/nfl_teams.csv").iloc[:,[1,2]]
    # tm_map["Name"] = tm_map.Name.replace({'NY': 'New York', 'Football Team': 'Commanders'}, regex=True)
    #
    # byes = pd.read_html("https://www.footballdiehards.com/nfl-bye-weeks.cfm")[0].dropna()
    # byes = byes.replace({"Giants Giants": "Giants", "Jets Jets": "Jets"}, regex=True)
    # byes = byes.assign(teams=byes['Teams'].str.split(',')).explode('teams').drop("Teams", axis=1)
    # byes["teams"] = byes.teams.str.strip()   # remove whitespace
    #
    # byes = pd.merge(byes, tm_map, left_on="teams", right_on="Name")
    # byes["week"] = byes['week'].apply(lambda x: x.split(" ")[-1]).astype(int)
    # byes["Abbreviation"] = byes.Abbreviation.str.upper()
    # byes['Abbreviation'] = byes.Abbreviation.replace({'JAX': 'JAC'})
    # byes = byes.rename({"week": "bye"}, axis=1)
    # byes = byes[["bye", "teams", "Abbreviation"]]

    return byes_dict


players_data = pd.merge(players_data, get_byes(season)[['bye', 'Abbreviation']],
                        left_on='team', right_on='Abbreviation', how='left')
players_data['bye'] = players_data.Abbreviation.map(get_byes(season))
auction_sims = pd.merge(sims, players_data[['player', 'bye']], on='player', how='left')
auction_sims['start_week'] = 1


def get_reference():
    # df = sims.copy()
    df2 = players_data.copy()

    # drafted = df[df['sim'] == sim].player.to_list()

    df2['ppg'] = np.where(df2.player == 'Alvin Kamara', df2.misc_fpts / 14, df2.misc_fpts / 17)
    df2['sd'] = np.where(df2.position == 'QB', df2.ppg*0.2, df2.ppg*0.4)

    return df2.groupby('position').quantile(0.8).reset_index()[['position', 'ppg', 'sd']]


def sim_injury(mean_games, pos):
    """
    :param pos: position of the player
    :return: the number of games missed by the player
    mean games missed by position comes from this study (adjusted by 1):
        https://www.profootballlogic.com/articles/nfl-injury-rate-analysis/
    """

    pos = pos.upper()
    if pos != 'DST':
        lower, upper, scale = 0, 18, mean_games[pos]
        x = stats.truncexpon(b=(upper - lower) / scale, loc=lower, scale=scale)
        games_missed = int(np.floor(x.rvs(1)[0]))

        if games_missed == 0:
            # print(np.nan)
            return []
        else:
            # print(list(np.sort(random.sample(range(1, upper), games_missed))))
            return list(np.sort(random.sample(range(1, upper), games_missed)))
    else:
        # print(np.nan)
        return []


def apply_wts(wt, pos):
    """
    :param wt: mean and standard deviation of position to draw a weight and apply to total points scored
    :param pos: the players position
    :return: randomly selected weight following a normal distribution, or 1 for DST.
    """
    pos = pos.upper()
    if pos != 'DST':
        wt_mean = wt[pos]['mean']
        wt_sd = wt[pos]['sd']
        return np.random.normal(wt_mean, wt_sd)
    else:
        return 1


def sim_scores(curr_sim_wk, teams, sim_data, posns, struc):
    # if current sim week is a bye, set proj ppg to 0
    sim_df = sim_data.copy()
    sim_df = sim_df[sim_df.ppg > 0]
    sim_df["ppg"] = np.where((curr_sim_wk == sim_df.bye), 0, sim_df.ppg)
    sim_df['sd'] = np.where(sim_df.position == 'QB', sim_df.ppg*0.2, sim_df.ppg*0.4)
    sim_df = sim_df[(sim_df.start_week <= curr_sim_wk) & (sim_df.bye != curr_sim_wk)]  # kamara suspended first 3 games
    sim_df = sim_df[~sim_df.missed.apply(lambda x: curr_sim_wk in x)]  # filter players who are injured that week

    ref = get_reference()

    # assign weights for projections
    ros_wt = 0.9
    rand_wt = round(1 - ros_wt, 1)

    # start simulation
    score_proj_df = pd.DataFrame()
    for tm in teams:
        # print(tm)
        pts = {
            'QB.proj': 0,
            'RB.proj': 0,
            'WR.proj': 0,
            'TE.proj': 0,
            'DST.proj': 0,
            'FLEX.proj': 0
        }

        # simulate through each position
        for pos, num in zip(posns, struc):
            # print(pos)
            if pos == "FLEX":
                fpos = ["RB", "WR"]
                fnum = [2, 3]
                flex = pd.DataFrame()
                for a, b in zip(fpos, fnum):
                    df = sim_df.query('team == @tm & position == @a').sort_values(by="ppg", ascending=False)
                    df = df.groupby("position").nth(b)
                    flex = flex.append(df)
                if flex.empty:
                    # add "free agent" reference player if flex position is empty
                    ref_flex = ref.query('position == @a')
                    flex = flex.append(ref_flex)

                # select flex player
                flex_play = flex.sort_values('ppg', ascending=False).head(1)
                # print(flex_play.ppg.values)
                flex_proj = flex_play.ppg
                flex_sd = flex_play.sd
                pts[pos + '.proj'] = np.random.normal(flex_proj, flex_sd)[0]
            else:
                week_proj = sim_df.query('team == @tm & position == @pos')
                week_proj = week_proj.append(ref.loc[ref.query('position == @pos').index.repeat(num)]).sort_values(by=["ppg"], ascending=False)
                proj = week_proj.head(num).ppg
                sd = week_proj.head(num).sd
                pts[pos + '.proj'] = np.random.normal(proj, sd).sum()
        # print("\n")

        # weight scores
        ros_proj = sum(pts.values()) * ros_wt

        # add general randomness, because fantasy football be like that
        rand_pts = random.uniform(100, 120) * rand_wt

        # combine projections
        total_proj_pts = ros_proj + rand_pts
        row = {
            'team': tm,
            'score': total_proj_pts
        }
        rowdf = pd.DataFrame(data=[row])

        score_proj_df = pd.concat([score_proj_df, rowdf])

    return score_proj_df.reset_index(drop=True)


def sim_matchups(regular_season_end=14):
    """
    Simulates rest of season matchups (top half wins) using
    scores from simulate_scores and returns final standings
    """

    # simulate scores for future weeks
    final_scores = pd.DataFrame()
    for curr_sim_wk in range(1, regular_season_end+1):
        score_sim = sim_scores(curr_sim_wk, teams, sim_data, posns, struc)
        score_sim['wins'] = np.where(score_sim.score > score_sim.score.median(), 1, 0)
        final_scores = pd.concat([final_scores, score_sim])

    return final_scores.groupby('team').agg({'wins': 'sum', 'score': 'sum'}).sort_values('wins', ascending=False)


def sim_season(teams):
    """
    Simulates regular season and playoffs. Returns number projected standings, win/rank distributions, and playoff projections
    """

    # initialize dictionaries to count number of occurances for each team
    n_playoffs = {key: 0 for key in teams}
    # n_finals = {key: 0 for key in teams}
    # n_champ = {key: 0 for key in teams}

    # simulate regular season
    results = sim_matchups()

    # top 5 by record, 6th by most points, rest by record
    top5 = results.sort_values(['wins', 'score'], ascending=False).head(5)
    sixth = results[~results.isin(top5)].dropna().sort_values(['score'], ascending=False).head(1)
    playoff_tms = pd.concat([top5, sixth])
    bot4 = results[~results.isin(playoff_tms)].dropna().sort_values(['wins'], ascending=False)
    results = pd.concat([playoff_tms, bot4])
    # results['rank'] = np.arange(len(results)) + 1

    # simulate plaoffs
    # get playoff teams
    p_teams = playoff_tms.reset_index().loc[:, "team"]

    # count playoff appearances
    for team in p_teams:
        n_playoffs[team] += 1

    # # simulate 1 week of semifinals
    # # top 3 teams get bye
    # byes = p_teams.head(2).values
    # quarter_teams = p_teams.iloc[2:]
    # quarter_scores = (sim_scores(15, quarter_teams, sim_data, posns, struc)
    #                   .set_index('team')
    #                   .reset_index()
    #                   .rename(columns={0: 'score'}))
    #
    # # get quarterfinals matchups and winners
    # # lower seed needs to win by 10 or more points
    # diff = 0
    # quarter_1 = quarter_scores.iloc[[0,3],:]
    # quarter_1 = np.where(quarter_1.score.iloc[1] - quarter_1.score.iloc[0] > diff, quarter_1.team.iloc[1], quarter_1.team.iloc[0]).astype(object)
    # quarter_2 = quarter_scores.iloc[[1,2],:]
    # quarter_2 = np.where(quarter_2.score.iloc[1] - quarter_2.score.iloc[0] > diff, quarter_2.team.iloc[1], quarter_2.team.iloc[0]).astype(object)
    #
    # # get semifinals matchups and winners
    # semi_teams = np.stack((quarter_1.item(), quarter_2.item())).astype(object)
    # semi_teams = np.concatenate((byes, semi_teams)).tolist()
    #
    # semi_scores = (sim_scores(16, semi_teams, sim_data, posns, struc)
    #                .set_index('team')
    #                .reset_index()
    #                .rename(columns={0: 'score'}))
    #
    # semi_1 = semi_scores.iloc[[0, 3]]
    # semi_2 = semi_scores.iloc[[1, 2]]
    #
    # # get finals matchup
    # final_1 = semi_1.sort_values(by='score', ascending=False).iloc[0, 0]
    # final_2 = semi_2.sort_values(by='score', ascending=False).iloc[0, 0]
    # finals = [final_1, final_2]
    #
    # # count finals appearances
    # for team in finals:
    #     n_finals[team] += 1
    #
    # # simulate 2 weeks of finals matchups
    # final_scores = (sim_scores(17, [final_1, final_2], sim_data, posns, struc)
    #                 .rename(columns={0: 'score'}))
    #
    # champ = final_scores[final_scores.team.isin(finals)].sort_values(by='score', ascending=False).iloc[0,0]
    #
    # # count championships and runner up
    # n_champ[champ] += 1
    #
    # # get playoff table
    # # convert dictionary counts to dataframes and combine
    playoffs = pd.DataFrame(n_playoffs.items(), columns=['team', 'n_playoffs'])
    # finals = pd.DataFrame(n_finals.items(), columns=['team', 'n_finals'])
    # champs = pd.DataFrame(n_champ.items(), columns=['team', 'n_champ'])
    #
    # dfs = [playoffs, finals, champs]
    #
    # playoff_sim = reduce(lambda left, right: pd.merge(left, right, on='team'), dfs)
    # playoff_sim = playoff_sim.set_index('team')
    #
    return pd.merge(results.reset_index(), playoffs, on='team')


# set parameters
teams = ['aaron', 'aditya', 'akshat', 'arjun', 'ayaz',
         'charles', 'faizan', 'hirsh', 'nick', 'varun']
posns = ["QB", "RB", "WR", "TE", "FLEX", "DST"]
struc = [1, 2, 3, 1, 1, 1]
mean_gms_missed = {'QB': 2.1, 'RB': 2.9, 'WR': 2.2, 'TE': 1.6}
wts = {'QB': {'mean': 0.9667, 'sd': 0.1690},
       'RB': {'mean': 1.0407, 'sd': 0.3855},
       'WR': {'mean': 1.0267, 'sd': 0.2586},
       'TE': {'mean': 0.9795, 'sd': 0.2370}}

ref = get_reference()
results_df = pd.DataFrame()
max_sim = 1_000
for i in range(1, max_sim+1):
    if i == 1:
        start = time()
        print(f"{datetime.now().strftime('%H:%M:%S')} | START SIM")

    # start = time()
    sim_data = auction_sims[auction_sims.sim == i]
    sim_data['missed'] = sim_data.apply(lambda row: sim_injury(mean_gms_missed, row['position']), axis=1)  # simulate injuries
    sim_data['ppg'] = sim_data.ppg * sim_data.apply(lambda row: apply_wts(wts, row['position']), axis=1)  # apply random weights
    results = sim_season(teams)
    results['sim'] = i
    results_df = pd.concat([results_df, results])
    end = time()
    # print(f"Sim {i}/{max_sim}: {round(end-start, 1)} seconds")

    if i == 100:
        print(f"{datetime.now().strftime('%H:%M:%S')} | Sim {i}/{max_sim}")
        last_time = time()
    if (i > 100) & (i % 100 == 0):
        print(f"{datetime.now().strftime('%H:%M:%S')} | Sim {i}/{max_sim}")
        last_time = time()

results_df.to_csv(r'./Outputs/sim_results_2023-08-26.csv', index=False)
# results_df = pd.read_csv(r'./Outputs/sim_results_2023-08-26.csv')

sims['slot_type'] = np.where(sims.slot == 'BENCH', 'BENCH', 'STARTER')
by_slot_type = sims.groupby(['sim', 'team', 'slot_type']).bid.sum().reset_index()
by_slot_type = by_slot_type[by_slot_type.slot_type != 'BENCH']
by_slot_type['STARTERS'] = by_slot_type.bid / 200

by_position = sims.groupby(['sim', 'team', 'slot']).bid.sum().reset_index()
by_position['p_alloc'] = by_position.bid / 200
by_position = by_position[~by_position.slot.isin(['DST', 'BENCH'])]
by_position = by_position.pivot(index=['sim', 'team'], columns='slot', values='p_alloc').reset_index()

spend_cats = pd.merge(by_slot_type[['sim', 'team', 'STARTERS']], by_position, on=['sim', 'team'])
total_spend = sims.groupby(['sim', 'team']).bid.sum().reset_index().rename(columns={'bid': 'TOTAL'})
spend_cats = pd.merge(total_spend, spend_cats, on=['sim', 'team'])

# results_df = results_df.reset_index()
df = pd.merge(results_df, spend_cats, on=['sim', 'team'])
df = df.set_index(['sim', 'team'])
df[['score', 'n_playoffs']].corr()

df[['n_playoffs', 'STARTERS']].boxplot(by='n_playoffs')
# df.STARTERS.plot.hist()
# df.groupby('n_playoffs').STARTERS.plot.boxplot()


def get_data(df, bins, col):
    col_upper = col.upper()

    data = df.copy()
    data[col+'_spend'] = pd.cut(data[col_upper]*200, bins=bins)
    poa = ((data.groupby(col+'_spend').n_playoffs.mean() / 0.5) - 1)
    # foa = ((data.groupby(col+'_spend').n_finals.mean() / (2/12)) - 1)
    # coa = ((data.groupby(col+'_spend').n_champ.mean() / (1/12)) - 1)
    ps = (data.groupby(col+'_spend').score.mean() - data.score.mean()) / 14

    # dfs = [poa, foa, coa, ps]
    dfs = [poa, ps]
    return reduce(lambda left, right: pd.merge(left, right, left_index=True, right_index=True), dfs)


def plot(data, bins_format, title, xlab, ylab):
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.bar(data.bins_str, data.score)
    ax.set_axisbelow(True)
    ax.yaxis.grid(c='lightgrey')
    ax.set_xticklabels(bins_format, rotation=15)
    plt.yticks(np.arange(-3, 3, 0.5))
    # ax.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1))
    plt.title(title)
    plt.xlabel(xlab)
    plt.ylabel(ylab)
    plt.savefig(r"./Outputs/wr_ppg.png", bbox_inches='tight')
    plt.show()


starters_bins = [0, 140, 150, 160, 170, 180, 190, 200]
starters_bins_format = ['<=140', '141-150', '151-160', '161-170', '171-180', '181-190', '191-200']
qb_bins = [0, 5, 10, 20, 30, 40, 200]
qb_bins_format = ['<=5', '6-10', '11-20', '21-30', '31-40', '41+']
rb_bins = [0, 20, 40, 60, 80, 100, 200]
rb_bins_format = ['<=20', '21-40', '41-60', '61-80', '81-100', '101+']
wr_bins = [0, 20, 40, 60, 80, 100, 200]
wr_bins_format = ['<=20', '21-40', '41-60', '61-80', '81-100', '101+']
te_bins = [0, 5, 10, 20, 40, 200]
te_bins_format = ['<=5', '6-10', '11-20', '21-40', '41+']
flex_bins = [0, 10, 20, 30, 40, 200]
flex_bins_format = ['<=10', '11-20', '21-30', '31-40', '40+']


pos = 'starters'
bins = starters_bins
bins_format = starters_bins_format

ycol = 'score'
# title = f'{pos.title()} by Playoff Odds Added'
title = f'{pos.upper()} by PPG Added'
file = fr'./Outputs/{pos}_ppga.png'
data = get_data(df, bins, pos).reset_index()
data['bins_str'] = data[pos+'_spend'].astype('str')
xlab = 'Total Spend'
ylab = 'Change in PPG'

fig, ax = plt.subplots(figsize=(5, 4))
ax.bar(data.bins_str, data[ycol])
ax.set_axisbelow(True)
# ax.yaxis.grid(c='lightgrey')
plt.axhline(y=0, c='black', linewidth=0.75)
ax.set_xticklabels(bins_format, rotation=15)
plt.yticks(np.arange(-2, 2, 0.5))
# plt.yticks(np.arange(-0.25, 0.25, 0.1))
# ax.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1))
plt.title(title)
plt.xlabel(xlab)
plt.ylabel(ylab)
plt.savefig(file, bbox_inches='tight')
# plt.show()



test = df.reset_index()
test['st_vs_med'] = test.groupby('sim')['STARTERS'].transform(lambda x: x - x.median())
test['score_diff'] = test.groupby('sim').score.transform(lambda x: x - x.mean()) / 14
# test = ((test.groupby('st_vs_med').score.mean() - test.score.mean()) / 14).reset_index()
a, b, c = np.polyfit(np.array(test.st_vs_med), np.array(test.score), 2)
fit_equation = lambda x: a * x ** 2 + b * x + c
X_fit = np.linspace(min(X), max(X), 1000)
Y_fit = f(X_fit)


X_data = np.array(test.st_vs_med)
Y_data = np.array(test.score_diff) / 14
a, b, c = np.polyfit(X_data, Y_data, 2)
fit_equation = lambda x: (a * (x ** 2)) + (b * x) + c

X_fit = np.linspace(min(X_data), max(X_data), 1000)
a, b, c = np.polyfit(X_data, Y_data, 2)
f = lambda x: (a * (x ** 2)) + (b * x) + c
Y_fit = f(X_fit)

fig, ax = plt.subplots()
ax.axhline(y=0, c='lightgrey', zorder=1)
ax.plot(X_fit, Y_fit, color='r', alpha=0.5, zorder=3)
ax.scatter(X_data, Y_data, s=4, color='lightgrey', zorder=2)
ax.xaxis.set_major_formatter(mtick.PercentFormatter(xmax=1))
plt.title('Team Starter Spend vs League Median')
plt.xlabel('Difference from League Median')
plt.ylabel('PPG Difference')
plt.show()


def spend_variation(col):
    X = df[col]*200
    Y = (df.score - df.score.median()) / 14
    norm = colors.TwoSlopeNorm(vcenter=0)
    fig, ax = plt.subplots()
    ax.scatter(x=X, y=Y, s=4, c=Y, norm=norm, cmap='coolwarm')
    ax.axhline(y=0, linestyle='dashed', linewidth=1, c='#B5B5B5')
    ax.xaxis.set_major_formatter('${x:1.0f}')
    plt.title(F'Variation in PPG by {col} Spend')
    plt.xlabel('Starter Spend')
    plt.ylabel('PPG Added')
    plt.show()


spend_variation('RB')


df['ppg_diff'] = (df.score - df.score.mean()) / 14
xcol = ['QB', 'RB', 'WR', 'TE', 'FLEX']
# line_color = ['lightgreen', 'blue', 'red', 'orange', 'darkgrey']
line_color = ['#B5D33D', '#6CA2EA', '#EB7D5B', '#FED23F', '#442288']

fig, ax = plt.subplots(figsize=(5, 4))
for col, color in zip(xcol, line_color):
    X = np.array(df[col]) * 200
    Y = (np.array(df['ppg_diff']))
    X_fit = np.linspace(min(X), max(X), 1000)
    a, b, c = np.polyfit(X, Y, 2)
    f = lambda x: (a * (x ** 2)) + (b * x) + c
    Y_fit = f(X_fit)
    x_ref = X_fit[np.where(Y_fit == Y_fit.max())[0][0]]
    ax.plot(X_fit, Y_fit, color=color, alpha=0.8, zorder=3, label=col)
    # plt.axvline(x=x_ref, color=color, linestyle='solid', alpha=0.3, ymax=Y_fit.max())
ax.grid(True, color='lightgrey')
ax.set_xlim([0, 200])
ax.set_ylim([0, 1.5])
plt.legend()
plt.xticks(np.arange(0, 140, 20))
plt.yticks(np.arange(0, 0.8, 0.1))
plt.title('Points Added Per Game by Position')
plt.xlabel('Spend ($)')
plt.ylabel('PPG Added')
plt.savefig(r'./Outputs/ppg_added.png', bbox_inches='tight')
plt.show()
