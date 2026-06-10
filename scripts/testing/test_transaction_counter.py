import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from scripts.utils.database import Database
from scripts.api.DataLoader import DataLoader
from scripts.utils import constants as const


def parse_args():
    parser = argparse.ArgumentParser(
        description="Print manager transaction counts for one season."
    )
    parser.add_argument("--season", type=int, default=2025)
    return parser.parse_args()


def read_table(table):
    return Database(table=table).retrieve_data(how="all")


def main():
    args = parse_args()
    season = args.season

    items = read_table("transaction_items")
    trades = read_table("trades")
    teams = read_table("fantasy_teams")

    for df, cols in [
        (items, ["season", "from_team_id", "to_team_id"]),
        (trades, ["season", "team_1_id", "team_2_id"]),
        (teams, ["season", "team_id"]),
    ]:
        for col in cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    season_items = items[
        (items["season"] == season)
        & (items["status"] == "EXECUTED")
    ].copy()
    season_trades = trades[trades["season"] == season].copy()
    season_teams = teams[teams["season"] == season][
        ["season", "team_id", "display_name", "team_name"]
    ].drop_duplicates()

    adds = (
        season_items[season_items["item_type"] == "ADD"]
        .groupby("to_team_id")
        .size()
        .reset_index(name="ACQ")
        .rename(columns={"to_team_id": "team_id"})
    )
    drops = (
        season_items[season_items["item_type"] == "DROP"]
        .groupby("from_team_id")
        .size()
        .reset_index(name="DROP")
        .rename(columns={"from_team_id": "team_id"})
    )
    trade_sides = pd.concat(
        [
            season_trades[["team_1_id"]].rename(columns={"team_1_id": "team_id"}),
            season_trades[["team_2_id"]].rename(columns={"team_2_id": "team_id"}),
        ],
        ignore_index=True,
    )
    trade_counts = (
        trade_sides
        .groupby("team_id")
        .size()
        .reset_index(name="TRADE")
    )

    counter = (
        season_teams
        .merge(adds, on="team_id", how="left")
        .merge(drops, on="team_id", how="left")
        .merge(trade_counts, on="team_id", how="left")
    )
    counter[["ACQ", "DROP", "TRADE"]] = counter[["ACQ", "DROP", "TRADE"]].fillna(0).astype(int)
    counter = counter.sort_values("display_name")

    print(f"Season {season} transaction counter from SQL")
    print(counter[["display_name", "team_name", "team_id", "TRADE", "ACQ", "DROP"]].to_string(index=False))
    print()
    print(f"Accepted trades in trades table: {len(season_trades)}")
    print(f"Trade side count total: {int(counter['TRADE'].sum())}")
    print(f"Executed ADD item total: {int(counter['ACQ'].sum())}")
    print(f"Executed DROP item total: {int(counter['DROP'].sum())}")

    official_cols = [
        "transaction_losses",
        "transaction_trades",
        "transaction_acquisitions",
        "transaction_drops",
    ]
    if all(col in teams.columns for col in official_cols):
        official = season_teams.merge(
            teams[["season", "team_id", *official_cols]],
            on=["season", "team_id"],
            how="left",
        )
        official = official.rename(
            columns={
                "transaction_losses": "LOSS",
                "transaction_trades": "TRADE",
                "transaction_acquisitions": "ACQ",
                "transaction_drops": "DROP",
            }
        )
        official[["LOSS", "TRADE", "ACQ", "DROP"]] = official[["LOSS", "TRADE", "ACQ", "DROP"]].fillna(0).astype(int)
        print("\nOfficial ESPN transactionCounter values stored in fantasy_teams")
        print(official[["display_name", "team_name", "team_id", "LOSS", "TRADE", "ACQ", "DROP"]].to_string(index=False))

    print("\nFantasy teams rows for requested season")
    print(teams[teams["season"] == season].to_string(index=False))

    print("\nRaw ESPN transactionCounter values")
    loader = DataLoader(
        year=season,
        league_id=const.LEAGUE_ID,
        swid=const.SWID,
        espn_s2=const.ESPN_S2,
    )
    raw_teams = loader.teams().get("teams", [])
    for team in raw_teams:
        print(
            {
                "team_id": team.get("id"),
                "abbrev": team.get("abbrev"),
                "primaryOwner": team.get("primaryOwner"),
                "transactionCounter": team.get("transactionCounter", {}),
            }
        )

    print("\nExecuted ADD/DROP breakdown by parent transaction type")
    breakdown = (
        season_items[season_items["item_type"].isin(["ADD", "DROP"])]
        .groupby(["transaction_type", "item_type"])
        .size()
        .reset_index(name="count")
        .sort_values(["transaction_type", "item_type"])
    )
    print(breakdown.to_string(index=False))

    raw_transactions = read_table("transactions")
    raw_transactions["season"] = pd.to_numeric(raw_transactions["season"], errors="coerce")
    raw_transactions["team_id"] = pd.to_numeric(raw_transactions["team_id"], errors="coerce")
    season_trade_transactions = raw_transactions[
        (raw_transactions["season"] == season)
        & raw_transactions["transaction_type"].astype(str).str.contains("TRADE", na=False)
    ].copy()

    print("\nRaw trade transaction breakdown")
    trade_breakdown = (
        season_trade_transactions
        .groupby(["transaction_type", "status", "execution_type"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["transaction_type", "status", "execution_type"])
    )
    print(trade_breakdown.to_string(index=False))

    print("\nRaw trade transactions by manager team_id")
    raw_trade_counter = (
        season_trade_transactions[season_trade_transactions["team_id"] > 0]
        .groupby(["team_id", "transaction_type", "status", "execution_type"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["team_id", "transaction_type", "status", "execution_type"])
    )
    print(raw_trade_counter.to_string(index=False))


if __name__ == "__main__":
    main()
