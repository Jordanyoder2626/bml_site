import argparse

import pandas as pd

from scripts.utils.database import Database


PICKUP_TYPES = ("FREEAGENT", "WAIVER")


def _read_table(table: str) -> pd.DataFrame:
    return Database(table=table).retrieve_data(how="all")


def _clean_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _load_pickup_inputs() -> dict[str, pd.DataFrame]:
    transaction_items = _read_table("transaction_items")
    transactions = _read_table("transactions")
    player_scores = _read_table("player_week_scores")
    fantasy_teams = _read_table("fantasy_teams")
    league_seasons = _read_table("league_seasons")

    transaction_items = _clean_numeric(
        transaction_items,
        [
            "season",
            "week",
            "player_id",
            "from_team_id",
            "to_team_id",
            "from_lineup_slot_id",
            "to_lineup_slot_id",
        ],
    )
    transactions = _clean_numeric(transactions, ["season", "week", "bid_amount"])
    player_scores = _clean_numeric(
        player_scores,
        ["season", "week", "player_id", "fantasy_team_id", "points"],
    )
    fantasy_teams = _clean_numeric(fantasy_teams, ["season", "team_id"])
    league_seasons = _clean_numeric(league_seasons, ["season", "pickup_eval_end_week"])

    return {
        "transaction_items": transaction_items,
        "transactions": transactions,
        "player_scores": player_scores,
        "fantasy_teams": fantasy_teams,
        "league_seasons": league_seasons,
    }


def _next_drop_week(add_row: pd.Series, drops: pd.DataFrame):
    matching_drops = drops[
        (drops["season"] == add_row["season"])
        & (drops["player_id"] == add_row["player_id"])
        & (drops["from_team_id"] == add_row["to_team_id"])
        & (drops["week"] > add_row["week"])
    ]

    if matching_drops.empty:
        return None

    return int(matching_drops["week"].min())


def pickup_ppg_records(min_games: int = 4, top_n: int | None = 25) -> pd.DataFrame:
    data = _load_pickup_inputs()
    items = data["transaction_items"]
    transactions = data["transactions"]
    scores = data["player_scores"]
    teams = data["fantasy_teams"]
    seasons = data["league_seasons"]

    adds = items[
        items["transaction_type"].isin(PICKUP_TYPES)
        & (items["status"] == "EXECUTED")
        & (items["item_type"] == "ADD")
        & (items["to_team_id"] > 0)
    ].copy()

    drops = items[
        items["transaction_type"].isin(PICKUP_TYPES)
        & (items["status"] == "EXECUTED")
        & (items["item_type"] == "DROP")
        & (items["from_team_id"] > 0)
    ].copy()

    if adds.empty:
        return pd.DataFrame()

    tx_cols = [
        "transaction_id",
        "bid_amount",
        "proposed_date",
        "process_date",
    ]
    adds = adds.merge(transactions[tx_cols], on="transaction_id", how="left")
    adds = adds.merge(
        seasons[["season", "pickup_eval_end_week"]],
        on="season",
        how="left",
    )
    adds["next_drop_week"] = adds.apply(lambda row: _next_drop_week(row, drops), axis=1)
    adds["end_week"] = adds["pickup_eval_end_week"]
    has_drop = adds["next_drop_week"].notna()
    adds.loc[has_drop, "end_week"] = (
        adds.loc[has_drop, ["next_drop_week", "pickup_eval_end_week"]]
        .min(axis=1)
        .astype(int)
    )

    leaderboard_rows = []
    for _, add in adds.iterrows():
        scoring_window = scores[
            (scores["season"] == add["season"])
            & (scores["player_id"] == add["player_id"])
            & (scores["fantasy_team_id"] == add["to_team_id"])
            & (scores["week"] > add["week"])
            & (scores["week"] <= add["end_week"])
            & (scores["points"] > 0)
        ].copy()

        games_played = len(scoring_window)
        if games_played < min_games:
            continue

        player_name = ""
        position = ""
        if "player_name" in scoring_window and not scoring_window.empty:
            player_name = scoring_window["player_name"].dropna().astype(str).iloc[0]
        if "position" in scoring_window and not scoring_window.empty:
            position_values = scoring_window["position"].dropna().astype(str)
            position = "" if position_values.empty else position_values.iloc[0]

        points = float(scoring_window["points"].sum())
        leaderboard_rows.append(
            {
                "season": int(add["season"]),
                "pickup_week": int(add["week"]),
                "end_week": int(add["end_week"]),
                "drop_week": (
                    None
                    if pd.isna(add["next_drop_week"])
                    else int(add["next_drop_week"])
                ),
                "transaction_type": add["transaction_type"],
                "transaction_id": add["transaction_id"],
                "team_id": int(add["to_team_id"]),
                "player_id": int(add["player_id"]),
                "player_name": player_name,
                "position": position,
                "games_played": games_played,
                "points": round(points, 2),
                "ppg": round(points / games_played, 2),
                "bid_amount": add.get("bid_amount", 0),
            }
        )

    leaderboard = pd.DataFrame(leaderboard_rows)
    if leaderboard.empty:
        return leaderboard

    leaderboard = leaderboard.merge(
        teams[["season", "team_id", "display_name", "team_name"]],
        on=["season", "team_id"],
        how="left",
    )
    leaderboard = leaderboard.sort_values(
        ["ppg", "points", "games_played"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    leaderboard.insert(0, "rank", range(1, len(leaderboard) + 1))

    if top_n:
        return leaderboard.head(top_n)

    return leaderboard


def _team_matchup_summary(matchups: pd.DataFrame,
                          team_name: str,
                          season: int,
                          trade_week: int,
                          end_week: int) -> dict:
    team_games = matchups[
        (matchups["season"] == season)
        & (matchups["team"] == team_name)
        & (matchups["week"] <= end_week)
    ].copy()
    before = team_games[team_games["week"] < trade_week]
    after = team_games[team_games["week"] > trade_week]

    def summary(df: pd.DataFrame) -> tuple[float, float, int]:
        if df.empty:
            return 0.0, 0.0, 0
        ppg = float(df["score"].mean())
        wins = float(df["matchup_result"].sum())
        games = int(len(df))
        win_pct = wins / games if games else 0.0
        return ppg, win_pct, games

    before_ppg, before_win_pct, before_games = summary(before)
    after_ppg, after_win_pct, after_games = summary(after)
    return {
        "before_ppg": before_ppg,
        "after_ppg": after_ppg,
        "ppg_delta": after_ppg - before_ppg,
        "before_win_pct": before_win_pct,
        "after_win_pct": after_win_pct,
        "win_pct_delta": after_win_pct - before_win_pct,
        "before_games": before_games,
        "after_games": after_games,
    }


def _traded_player_value(scores: pd.DataFrame,
                         season: int,
                         week: int,
                         end_week: int,
                         team_id: int,
                         player_ids: list[int],
                         player_names: dict[int, str]) -> dict:
    if not player_ids:
        return {"points": 0.0, "games": 0, "ppg": 0.0, "players": ""}

    scoring_window = scores[
        (scores["season"] == season)
        & (scores["week"] > week)
        & (scores["week"] <= end_week)
        & (scores["fantasy_team_id"] == team_id)
        & (scores["player_id"].isin(player_ids))
        & (scores["points"] != 0)
    ].copy()

    points = float(scoring_window["points"].sum()) if not scoring_window.empty else 0.0
    games = int(len(scoring_window))
    ppg = points / games if games else 0.0
    players = [player_names.get(player_id, str(player_id)) for player_id in player_ids]
    return {
        "points": points,
        "games": games,
        "ppg": ppg,
        "players": ", ".join(players),
    }


def _trade_side_rows(trades: pd.DataFrame,
                     trade_items: pd.DataFrame,
                     scores: pd.DataFrame,
                     teams: pd.DataFrame,
                     seasons: pd.DataFrame,
                     matchups: pd.DataFrame) -> pd.DataFrame:
    rows = []
    team_names = teams[["season", "team_id", "display_name"]].drop_duplicates()
    player_names = (
        scores[["player_id", "player_name"]]
        .dropna()
        .drop_duplicates("player_id")
        .set_index("player_id")["player_name"]
        .astype(str)
        .to_dict()
    )

    for _, trade in trades.iterrows():
        season = int(trade["season"])
        week = int(trade["week"])
        season_row = seasons[seasons["season"] == season]
        end_week = (
            int(season_row["pickup_eval_end_week"].iloc[0])
            if not season_row.empty and not pd.isna(season_row["pickup_eval_end_week"].iloc[0])
            else 15 if season <= 2020 else 16
        )
        items = trade_items[trade_items["trade_id"] == trade["trade_id"]]
        if items.empty:
            continue

        trade_team_ids = sorted(
            set(items["from_team_id"].dropna().astype(int))
            | set(items["to_team_id"].dropna().astype(int))
        )
        for team_id in trade_team_ids:
            acquired = items[items["to_team_id"] == team_id]["player_id"].dropna().astype(int).tolist()
            sent = items[items["from_team_id"] == team_id]["player_id"].dropna().astype(int).tolist()
            value = _traded_player_value(
                scores,
                season,
                week,
                end_week,
                team_id,
                acquired,
                player_names,
            )

            team_row = team_names[
                (team_names["season"] == season)
                & (team_names["team_id"] == team_id)
            ]
            team_name = "" if team_row.empty else str(team_row["display_name"].iloc[0])
            matchup_summary = _team_matchup_summary(matchups, team_name, season, week, end_week)

            rows.append(
                {
                    "trade_id": trade["trade_id"],
                    "season": season,
                    "week": week,
                    "team_id": team_id,
                    "team": team_name,
                    "players_acquired": value["players"],
                    "players_sent": ", ".join(
                        player_names.get(player_id, str(player_id))
                        for player_id in sent
                    ),
                    "player_points_after": value["points"],
                    "player_games_after": value["games"],
                    "player_ppg_after": value["ppg"],
                    "players_acquired_count": len(acquired),
                    "players_sent_count": len(sent),
                    **matchup_summary,
                }
            )

    return pd.DataFrame(rows)


def trade_vault_records() -> dict[str, pd.DataFrame]:
    trades = _clean_numeric(_read_table("trades"), ["season", "week", "team_1_id", "team_2_id"])
    trade_items = _clean_numeric(
        _read_table("trade_items"),
        ["season", "week", "player_id", "from_team_id", "to_team_id"],
    )
    scores = _clean_numeric(
        _read_table("player_week_scores"),
        ["season", "week", "player_id", "fantasy_team_id", "points"],
    )
    teams = _clean_numeric(_read_table("fantasy_teams"), ["season", "team_id"])
    seasons = _clean_numeric(_read_table("league_seasons"), ["season", "pickup_eval_end_week"])
    matchups = _clean_numeric(
        _read_table("matchups"),
        ["season", "week", "score", "matchup_result"],
    )

    if trades.empty or trade_items.empty:
        return {
            "lopsided": pd.DataFrame(),
            "even": pd.DataFrame(),
            "mutual_benefit": pd.DataFrame(),
            "mutual_destruction": pd.DataFrame(),
        }

    side_rows = _trade_side_rows(trades, trade_items, scores, teams, seasons, matchups)
    if side_rows.empty:
        return {
            "lopsided": pd.DataFrame(),
            "even": pd.DataFrame(),
            "mutual_benefit": pd.DataFrame(),
            "mutual_destruction": pd.DataFrame(),
        }

    records = []
    for trade_id, group in side_rows.groupby("trade_id"):
        if len(group) != 2:
            continue
        group = group.sort_values("team").reset_index(drop=True)
        first = group.iloc[0]
        second = group.iloc[1]
        week = int(first["week"])
        if week < 4:
            continue

        if (group["before_games"] < 3).any() or (group["after_games"] < 2).any():
            continue

        first_delta = float(first["ppg_delta"])
        second_delta = float(second["ppg_delta"])
        lopsided_score = abs(first_delta - second_delta)
        mutual_benefit_score = min(first_delta, second_delta)
        mutual_destruction_score = first_delta + second_delta
        mutual_benefit_eligible = first_delta > 0 and second_delta > 0
        mutual_destruction_eligible = first_delta < 0 and second_delta < 0

        records.append(
            {
                "trade_id": trade_id,
                "season": int(first["season"]),
                "week": week,
                "team_1": first["team"],
                "team_2": second["team"],
                "team_1_received": first["players_acquired"],
                "team_2_received": second["players_acquired"],
                "dedupe_key": "|".join(
                    [
                        str(int(first["season"])),
                        str(week),
                        "|".join(sorted([str(first["team"]), str(second["team"])])),
                        "|".join(
                            sorted(
                                [
                                    player.strip()
                                    for players in [first["players_acquired"], second["players_acquired"]]
                                    for player in str(players).split(",")
                                    if player.strip()
                                ]
                            )
                        ),
                    ]
                ),
                "team_1_before_ppg": float(first["before_ppg"]),
                "team_1_after_ppg": float(first["after_ppg"]),
                "team_1_ppg_delta": first_delta,
                "team_2_before_ppg": float(second["before_ppg"]),
                "team_2_after_ppg": float(second["after_ppg"]),
                "team_2_ppg_delta": second_delta,
                "lopsided_score": lopsided_score,
                "mutual_benefit_score": mutual_benefit_score,
                "mutual_destruction_score": mutual_destruction_score,
                "mutual_benefit_eligible": mutual_benefit_eligible,
                "mutual_destruction_eligible": mutual_destruction_eligible,
            }
        )

    records_df = pd.DataFrame(records)
    if records_df.empty:
        return {
            "lopsided": pd.DataFrame(),
            "even": pd.DataFrame(),
            "mutual_benefit": pd.DataFrame(),
            "mutual_destruction": pd.DataFrame(),
        }
    records_df = (
        records_df
        .sort_values(["season", "week", "trade_id"])
        .drop_duplicates("dedupe_key")
        .reset_index(drop=True)
    )

    def top_trade_ids(sort_col: str,
                      ascending: bool,
                      top_n: int = 5,
                      eligibility_col: str | None = None) -> list:
        one_row_per_trade = records_df.drop_duplicates("trade_id").copy()
        if eligibility_col:
            one_row_per_trade = one_row_per_trade[one_row_per_trade[eligibility_col]]
        one_row_per_trade = one_row_per_trade.sort_values(sort_col, ascending=ascending).head(top_n)
        return one_row_per_trade["trade_id"].tolist()

    def rows_for_trade_ids(trade_ids: list) -> pd.DataFrame:
        rows = records_df[records_df["trade_id"].isin(trade_ids)].copy()
        rows["trade_order"] = rows["trade_id"].map(
            {trade_id: idx for idx, trade_id in enumerate(trade_ids, start=1)}
        )
        return rows.sort_values("trade_order")

    return {
        "lopsided": rows_for_trade_ids(
            top_trade_ids("lopsided_score", ascending=False, top_n=10)
        ),
        "even": rows_for_trade_ids(
            top_trade_ids("lopsided_score", ascending=True, top_n=5)
        ),
        "mutual_benefit": rows_for_trade_ids(
            top_trade_ids(
                "mutual_benefit_score",
                ascending=False,
                eligibility_col="mutual_benefit_eligible",
            )
        ),
        "mutual_destruction": rows_for_trade_ids(
            top_trade_ids(
                "mutual_destruction_score",
                ascending=True,
                eligibility_col="mutual_destruction_eligible",
            )
        ),
    }


def transaction_counter_records() -> pd.DataFrame:
    teams = _clean_numeric(
        _read_table("fantasy_teams"),
        [
            "transaction_trades",
            "transaction_acquisitions",
            "transaction_drops",
        ],
    )
    counter = (
        teams
        .groupby("display_name", as_index=False)[
            [
                "transaction_trades",
                "transaction_acquisitions",
                "transaction_drops",
            ]
        ]
        .sum()
        .rename(
            columns={
                "display_name": "Manager",
                "transaction_trades": "Trades",
                "transaction_acquisitions": "Acq",
                "transaction_drops": "Drop",
            }
        )
    )
    counter[["Trades", "Acq", "Drop"]] = counter[["Trades", "Acq", "Drop"]].fillna(0).astype(int)
    counter["Total"] = counter["Trades"] + counter["Acq"] + counter["Drop"]

    return (
        counter[["Manager", "Trades", "Acq", "Drop", "Total"]]
        .sort_values(["Total", "Acq", "Drop", "Trades"], ascending=False)
        .reset_index(drop=True)
    )


def favorite_player_records(top_n: int = 5) -> list[dict]:
    """Return each manager's most frequently rostered players by distinct season."""
    scores = _clean_numeric(
        _read_table("player_week_scores"),
        ["season", "player_id", "fantasy_team_id"],
    )
    teams = _clean_numeric(
        _read_table("fantasy_teams"),
        ["season", "team_id"],
    )

    if scores.empty or teams.empty:
        return []

    rostered = scores[
        scores["player_id"].notna()
        & scores["fantasy_team_id"].notna()
        & scores["player_name"].notna()
        & ~scores["position"].fillna("").str.upper().isin(["DST", "D/ST", "DEF"])
    ].copy()
    rostered = rostered.merge(
        teams[["season", "team_id", "owner_id", "display_name"]],
        left_on=["season", "fantasy_team_id"],
        right_on=["season", "team_id"],
        how="inner",
    )

    manager_names = (
        teams
        .sort_values("season")
        .drop_duplicates("owner_id", keep="last")
        .set_index("owner_id")["display_name"]
        .to_dict()
    )
    rostered["manager"] = rostered["owner_id"].map(manager_names)

    # Some managers have had more than one ESPN owner ID. Consolidate those IDs
    # under the displayed person before counting and ranking their players.
    # This also reduces weekly appearances or multiple stints to one player-year.
    rostered = rostered.drop_duplicates(["manager", "season", "player_id"])
    counts = (
        rostered
        .groupby(["manager", "player_id"], as_index=False)
        .agg(player_name=("player_name", "last"), years=("season", "nunique"))
    )
    counts = counts[counts["manager"].str.casefold() != "peyton"]
    counts = counts.sort_values(
        ["manager", "years", "player_name"],
        ascending=[True, False, True],
    )
    counts["rank"] = counts.groupby("manager").cumcount() + 1
    counts = counts[counts["rank"] <= top_n]

    favorites = []
    for manager, group in counts.groupby("manager", sort=True):
        players = [
            f"{row.player_name} ({int(row.years)} {'year' if row.years == 1 else 'years'})"
            for row in group.itertuples()
        ]
        favorites.append({"manager": manager, "players": players})

    return favorites


def parse_args():
    parser = argparse.ArgumentParser(
        description="Print best waiver/free-agent pickups by post-pickup PPG."
    )
    parser.add_argument("--min-games", type=int, default=4)
    parser.add_argument("--top", type=int, default=25)
    return parser.parse_args()


def main():
    args = parse_args()
    records = pickup_ppg_records(min_games=args.min_games, top_n=args.top)

    if records.empty:
        print("No pickup records found.")
        return

    display_cols = [
        "rank",
        "season",
        "pickup_week",
        "end_week",
        "drop_week",
        "player_name",
        "display_name",
        "team_name",
        "transaction_type",
        "games_played",
        "points",
        "ppg",
        "bid_amount",
    ]
    print(records[display_cols].to_string(index=False))


if __name__ == "__main__":
    main()
