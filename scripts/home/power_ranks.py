import numpy as np
import math

from scripts.utils.database import Database
from scripts.api.Settings import Params


def linear_decay(x, r):
    """Calculates weights for each week using an linear decay function"""
    return r / ((x * (x + 1)) / 2)


def exp_decay(week: int, r=3, reverse=False) -> list:
    """Calculates weights for each week using an exponential decay function"""

    wts = []
    for w in range(1, week+1):
        if reverse:
            wts.append(math.exp(-w * 1/r))
        else:
            wts.append(math.exp(w * 1/r))

    return [(w/sum(wts)) for w in wts]


def scoring_index(score, median, weight):
    return (score / median) * weight


def consistency_index(sd, ppg, ppg_median):
    return (1 - (sd / ppg)) * (ppg / ppg_median)


def scale_luck(x, from_min=-1, from_max=1, to_min=0, to_max=1):
    return (x - from_min) * (to_max - to_min) / (from_max - from_min) + to_min


def power_rank(params: Params,
               season: int,
               week: int):

    wks_played_factor = week / params.regular_season_end
    wks_rem_factor = (params.regular_season_end - week) / params.regular_season_end

    eff = Database(table='efficiency', season=season, week=week).retrieve_data(how='season')
    h2h = Database(table='h2h', season=season, week=week).retrieve_data(how='season')
    ss = Database(table='schedule_switcher', season=season, week=week).retrieve_data(how='season')
    season_sim = Database(table='season_sim', season=season, week=week+1).retrieve_data(how='week')
    matchups = Database(table='matchups', season=season, week=week).retrieve_data(how='season')
    matchups = matchups[matchups.week <= params.regular_season_end]
    if matchups.empty:
        return {}

    matchups['median'] = matchups.groupby('week')['score'].transform('median')

    if week == 1:
        ts_idx_wt = 0.45
        ws_idx_wt = 0.45
        c_idx_wt  = 0.00
        l_idx_wt  = 0.05
        m_idx_wt  = 0.05
    else:
        ts_idx_wt = 0.40
        ws_idx_wt = 0.30
        c_idx_wt  = 0.15
        m_idx_wt  = 0.10
        l_idx_wt  = 0.05

    consistency_factor = 1 if week >= 5 else week / 5

    # ---------- FIX 1: safe median for empty season_sim ----------
    if season_sim is None or len(season_sim) == 0:
        sim_ppg_med = 0
    else:
        sim_ppg_med = (season_sim.total_points.median() / params.regular_season_end) * wks_rem_factor

    ppg_med = matchups.groupby('team').score.mean().median() * wks_played_factor
    if (
        eff.empty
        or 'actual_lineup_score' not in eff.columns
        or 'optimal_lineup_score' not in eff.columns
        or eff.groupby('team').optimal_lineup_score.mean().median() == 0
    ):
        eff_med = 1
    else:
        eff_med = eff.groupby('team').actual_lineup_score.mean().median() / eff.groupby('team').optimal_lineup_score.mean().median()

    wts = exp_decay(week=week, reverse=False)

    pr_dict = {}
    c_scores = {}
    l_scores = {}

    for t in set(matchups.team):

        pr_tm = matchups[matchups.team == t]
        pr_tm_sim = season_sim[season_sim.team == t]

        # ---------- FIX 2: safe .values[0] ----------
        if pr_tm_sim is not None and len(pr_tm_sim) > 0:
            sim_val = pr_tm_sim.total_points.values[0]
        else:
            sim_val = pr_tm.score.mean()

        tm_ppg = (pr_tm.score.mean() * wks_played_factor) + ((sim_val / params.regular_season_end) * wks_rem_factor)
        tm_score_index = scoring_index(tm_ppg, sim_ppg_med + ppg_med, weight=1)
        pr_dict[t] = {'season_idx': tm_score_index.item()}

        scores = []
        for wk in range(1, week+1):
            pr_wk = pr_tm[pr_tm.week == wk]

            if pr_wk is None or len(pr_wk) == 0:
                continue

            wk_med = pr_wk['median'].values[0]
            wk_t_score = pr_wk.score.values[0]
            wk_wt = wts[wk-1]

            s_idx = scoring_index(score=wk_t_score, median=wk_med, weight=wk_wt)
            scores.append(s_idx)

        pr_dict[t].update({'week_idx': sum(scores)})

        tm_m_wp = matchups[matchups.team==t].matchup_result.sum() / week
        ss_wp = 0 if ss.empty or 'result' not in ss.columns else ss[(ss.team==t) & (ss.schedule_of!=t)].result.sum() / ((len(set(matchups.team))-1) * week)
        tm_m_luck = scale_luck(tm_m_wp - ss_wp)

        tm_th_wp = matchups[matchups.team==t].tophalf_result.sum() / week
        th_wp = 0 if h2h.empty or 'result' not in h2h.columns else h2h[h2h.team==t].result.sum() / ((len(set(matchups.team))-1) * week)
        tm_th_luck = scale_luck(tm_th_wp - th_wp)

        l_scores[t] = tm_m_luck + tm_th_luck
        pr_dict[t].update({'luck_idx': (tm_m_luck + tm_th_luck) / 2})

        sd = pr_tm.score.std()
        tm_ppg_cons = pr_tm.score.mean()
        c_idx = 0 if len(pr_tm) < 2 else consistency_index(sd=sd, ppg=tm_ppg_cons, ppg_median=ppg_med)
        c_scores[t] = c_idx * consistency_factor

        if eff.empty or 'team' not in eff.columns or 'optimal_lineup_score' not in eff.columns or 'actual_lineup_score' not in eff.columns:
            lineup_eff = 1
        else:
            tm_eff = eff[eff.team==t]
            den = tm_eff.optimal_lineup_score.sum()
            lineup_eff = tm_eff.actual_lineup_score.sum() / den if den != 0 else 1
        m_idx = scoring_index(score=lineup_eff, median=eff_med, weight=1)
        pr_dict[t].update({'manager_idx': m_idx})

    for t in set(matchups.team):
        if week > 2:
            c_idx = scoring_index(score=c_scores[t],
                                  median=np.median([c for c in c_scores.values()]),
                                  weight=1)
            pr_dict[t].update({'consistency_idx': c_idx})
        else:
            pr_dict[t].update({'consistency_idx': 1})

    for t in set(matchups.team):
        total_score = (pr_dict[t]['season_idx'] * wks_rem_factor * ts_idx_wt) \
                      + (pr_dict[t]['week_idx'] * wks_played_factor * ws_idx_wt) \
                      + (pr_dict[t]['consistency_idx'] * c_idx_wt) \
                      + (pr_dict[t]['manager_idx'] * m_idx_wt) \
                      + (pr_dict[t]['luck_idx'] * wks_played_factor * l_idx_wt)

        pr_dict[t].update({'power_score_raw': total_score})

    meds = []
    for _, inner_dict in pr_dict.items():
        meds.append(inner_dict['power_score_raw'])

    med = np.median(meds).item()

    for k, v in pr_dict.items():
        pr_dict[k].update({'power_score_norm': v['power_score_raw'] / med})

    sorted_pr_norm = dict(sorted(pr_dict.items(),
                                 key=lambda item: item[1]['power_score_norm']))

    return sorted_pr_norm
