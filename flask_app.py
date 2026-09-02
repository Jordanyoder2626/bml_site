from flask import Flask, render_template, send_from_directory
from flask_fontawesome import FontAwesome

import scripts.utils.utils as ut
from data_prep import *
from scripts.records.transaction_records import (
    favorite_player_records,
    pickup_ppg_records,
    transaction_counter_records,
)
from scripts.utils.constants import STANDINGS_COLUMNS_FLASK, RECORDS_COLUMNS_FLASK, ALLTIME_COLUMNS_FLASK


# create flask app
app = Flask(__name__)
fa = FontAwesome(app)
transaction_vault_cache = None
favorite_players_cache = None
transaction_vault_page_cache = None
transaction_counter_cache = None

###########################
# Flask routes
##########################

@app.route("/")
def home():
    week_str = f'Week {params.current_week}'
    standings_columns = list(STANDINGS_COLUMNS_FLASK)
    headings_st = ['Rk', 'Team', 'Overall', 'Division', 'Win%', 'Points', 'Bye GB', 'Playoff GB']
    if show_bootyman_status:
        standings_columns.append('bootyman_status')
        headings_st.append('BMB GB')
    headings_st = tuple(headings_st)
    data_st = ut.flask_get_data(standings_df[standings_columns])

    data_prev = ut.flask_get_data(previous_week_results)

    data_current = ut.flask_get_data(current_week_matchup_rows)

    show_scenarios = params.current_week <= params.regular_season_end
    scenario_cols = ['Scenario', 'Probability']
    headings_cl = tuple(scenario_cols) if show_scenarios and clinches['clinches'] else tuple()
    data_cl = ut.flask_get_data(clinches['clinches']) if show_scenarios and clinches['clinches'] else tuple()

    headings_el = tuple(scenario_cols) if show_scenarios and clinches['eliminations'] else tuple()
    data_el = ut.flask_get_data(clinches['eliminations']) if show_scenarios and clinches['eliminations'] else tuple()

    headings_bb = tuple(scenario_cols) if show_scenarios and clinches['bootyman'] else tuple()
    data_bb = ut.flask_get_data(clinches['bootyman']) if show_scenarios and clinches['bootyman'] else tuple()

    return render_template(
        "home.html", week=week_str,
        headings_st=headings_st, data_st=data_st,
        data_prev=data_prev,
        data_current=data_current,
        headings_cl=headings_cl, data_cl=data_cl,
        headings_el=headings_el, data_el=data_el,
        headings_bb=headings_bb, data_bb=data_bb,
        previous_week=previous_week,
        current_week=params.current_week,
        previous_week_low_score=previous_week_low_score,
        last_week_bootyman=last_week_bootyman,
        is_playoff_week=is_playoff_week,
        east_division_team_names=EAST_DIVISION_TEAM_NAMES,
        show_bootyman_status=show_bootyman_status,
        postseason_home=postseason_home
    )

@app.route("/power-rankings/")
def power_rankings():
    week_str = f'Week {week}'
    power_week_str = power_display_week

    show_power_rankings = not pr_table.empty
    headings_pr = tuple(['Team', 'Season', 'Recency', 'Consistency', 'Manager', 'Luck', 'Rank', '1 Week \u0394', 'Score', '1 Week \u0394'])
    data_pr = ut.flask_get_data(pr_table[pr_cols]) if show_power_rankings else tuple()

    return render_template(
        "powerrank.html", week=week_str,
        headings_pr=headings_pr, data_pr=data_pr,
        show_power_rankings=show_power_rankings,
        power_week=power_week_str,
        rank_data=rank_data
    )

@app.route("/logos/<path:filename>")
def logos(filename):
    return send_from_directory("logos", filename)

@app.route("/simulations/")
def sims():
    if params.current_week > params.regular_season_end:
        headings_bets = tuple(['Team', 'Proj Points', 'Matchup'])
        data_bets = ut.flask_get_data(betting_table[['team', 'avg_score', 'p_win']])
    else:
        headings_bets = tuple(['Team', 'Proj Points', 'Matchup', 'Highest', 'Lowest'])
        data_bets = ut.flask_get_data(betting_table[['team', 'avg_score', 'p_win', 'p_highest', 'p_lowest']])

    headings_season_sim = tuple(['Team', 'Projected Wins', 'Projected Losses', 'Points', 'Playoff%', 'Finals%', 'Champion%'])
    data_season_sim = ut.flask_get_data(season_sim_table)

    headings_w = tuple(season_sim_wins_table.columns)
    data_w = ut.flask_get_data(season_sim_wins_table)
    # team_df = season_sim_wins_table[['Team']]
    # wins_df = season_sim_wins_table.iloc[:, 1:]
    # wins_df.columns = wins_df.columns.astype(str)
    # scaler = MinMaxScaler()
    # normalized_df = pd.DataFrame(scaler.fit_transform(wins_df), columns=wins_df.columns)
    # win_colors_df = pd.merge(team_df, normalized_df, left_index=True, right_index=True)
    # colors_w = ut.flask_get_data(win_colors_df)

    headings_r = tuple(season_sim_ranks_table.columns)
    data_r = ut.flask_get_data(season_sim_ranks_table)
    # team_df = season_sim_ranks_table[['Team']]
    # ranks_df = season_sim_ranks_table.iloc[:, 1:]
    # ranks_df.columns = ranks_df.columns.astype(str)
    # scaler = MinMaxScaler()
    # normalized_df = pd.DataFrame(scaler.fit_transform(ranks_df), columns=ranks_df.columns)
    # rank_colors_df = pd.merge(team_df, normalized_df, left_index=True, right_index=True)
    # colors_r = ut.flask_get_data(rank_colors_df)

    return render_template(
        "simulations.html", week=f'Week {week}',
        headings_bets=headings_bets, data_bets=data_bets,
        headings_s=headings_season_sim, data_s=data_season_sim,
        headings_w=headings_w, data_w=data_w,
        headings_r=headings_r, data_r=data_r,
        # headings_p=headings_p, data_p=data_p,
        tstamp_bets=timestamp_betting, tstamp_s=timestamp_season_sim,
        show_season_sim=params.current_week <= params.regular_season_end,
        east_division_team_names=EAST_DIVISION_TEAM_NAMES
    )

@app.route("/scenarios/")
def scenarios():
    headings_h2h = tuple(
        ut.flatten_list(
            [
                ['Team'], list(wins_vs_opp.columns[1:len(teams.team_ids)+1]), ['Record', 'Win%']
            ]
        )
    )
    data_h2h = ut.flask_get_data(wins_vs_opp)

    headings_wk = tuple(
        ut.flatten_list(
            [
                ['Team'], list(wins_by_week.columns[1:-2]), ['# First', '# Last']
            ]
        )
    )
    data_wk = ut.flask_get_data(wins_by_week)
    data_styled = ut.flask_get_data([
        [
            f'<span class="perfect-week">{cell}</span>' if cell.endswith('-0')
            else f'<span class="winless-week">{cell}</span>' if cell.startswith('0-')
            else cell
            for cell in row
        ]
        for row in data_wk
    ])

    headings_ss = tuple(ut.flatten_list([['Team'], list(ss_disp.columns[1:len(teams.team_ids)+2])]))
    data_ss = ut.flask_get_data(ss_disp)

    return render_template("scenarios.html",
                           headings_h2h=headings_h2h, data_h2h=data_h2h,
                           headings_wk=headings_wk, data_wk=data_styled,
                           headings_ss=headings_ss, data_ss=data_ss)

@app.route("/efficiency/")
def eff():
    return render_template(
        "efficiencies.html",
        eff_plot=eff_plot,
        efficiency_title=efficiency_title
    )

@app.route("/efficiency/<path:filename>")
def efficiency_image(filename):
    return send_from_directory("efficiency", filename)

@app.route("/champions/")
def champs():
    headings_pc = tuple(prev_champs.columns)
    data_pc = ut.flask_get_data(prev_champs)

    headings_cc = tuple(champ_count.columns)
    data_cc = ut.flask_get_data(champ_count)

    return render_template("champions.html",
                           headings_pc=headings_pc, data_pc=data_pc,
                           headings_cc=headings_cc, data_cc=data_cc)

@app.route("/bootymen/")
def bootymen():
    headings_pb = tuple(prev_bootymen.columns)
    data_pb = ut.flask_get_data(prev_bootymen)

    headings_bc = tuple(bootyman_count.columns)
    data_bc = ut.flask_get_data(bootyman_count)

    return render_template("bootymen.html",
                           headings_pb=headings_pb, data_pb=data_pb,
                           headings_bc=headings_bc, data_bc=data_bc)

@app.route("/records/")
def records():
    headings_alltime = tuple(['Team', 'Seasons', 'Playoffs', 'Overall', 'Win%', 'Points'])
    data_alltime = ut.flask_get_data(alltime_df[ALLTIME_COLUMNS_FLASK])

    headings_matchups = tuple(alltime_matchups_df.columns)
    data_matchups = ut.flask_get_data(alltime_matchups_df)

    headings_rec = tuple(['Category', 'Record', 'Holder', 'Season', 'Week'])
    data_rec = ut.flask_get_data(records_df[RECORDS_COLUMNS_FLASK])

    return render_template("records.html",
                           headings_alltime=headings_alltime, data_alltime=data_alltime,
                           headings_matchups=headings_matchups, data_matchups=data_matchups,
                           headings_rec=headings_rec, data_rec=data_rec)

@app.route("/transaction-vault/")
def transaction_vault():
    global transaction_vault_cache
    global favorite_players_cache
    global transaction_vault_page_cache
    global transaction_counter_cache
    if transaction_vault_page_cache is not None:
        return render_template("transaction_vault.html", **transaction_vault_page_cache)

    if transaction_vault_cache is None:
        transaction_vault_cache = pickup_ppg_records(top_n=None)
    if favorite_players_cache is None:
        favorite_players_cache = favorite_player_records(top_n=5)
    if transaction_counter_cache is None:
        transaction_counter_cache = transaction_counter_records()

    pickup_records = transaction_vault_cache
    favorite_players = favorite_players_cache
    transaction_counter = transaction_counter_cache
    headings = tuple(['Rank', 'Season', 'Player Name', 'Week Picked Up', 'PPG After Pickup', 'Team'])
    headings_counter = tuple(transaction_counter.columns)
    data_counter = ut.flask_get_data(transaction_counter)

    if pickup_records.empty:
        data_qb = tuple()
        data_non_qb = tuple()
    else:
        display_cols = ['rank', 'season', 'player_name', 'pickup_week', 'ppg', 'display_name']
        pickup_records = pickup_records.copy()
        pickup_records['ppg'] = pickup_records['ppg'].map('{:.2f}'.format)

        qb_records = pickup_records[pickup_records['position'] == 'QB'].head(15).copy()
        non_qb_records = pickup_records[
            ~pickup_records['position'].isin(['QB', 'K', 'DST'])
        ].head(25).copy()

        qb_records['rank'] = range(1, len(qb_records) + 1)
        non_qb_records['rank'] = range(1, len(non_qb_records) + 1)

        data_qb = ut.flask_get_data(qb_records[display_cols])
        data_non_qb = ut.flask_get_data(non_qb_records[display_cols])

    transaction_vault_page_cache = {
        "headings_qb": headings,
        "data_qb": data_qb,
        "headings_non_qb": headings,
        "data_non_qb": data_non_qb,
        "headings_favorites": ("Manager", "Favorite #1", "Favorite #2", "Favorite #3", "Favorite #4", "Favorite #5"),
        "favorite_players": favorite_players,
        "headings_counter": headings_counter,
        "data_counter": data_counter,
    }

    return render_template("transaction_vault.html", **transaction_vault_page_cache)

# Run app
if __name__ == "__main__":
    app.run()
