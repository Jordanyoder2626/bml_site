import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from scripts.api.DataLoader import DataLoader
from scripts.utils import constants as const
from scripts.utils.database import Database


SCHEMA_FILES = [
    "league_seasons.sql",
    "fantasy_teams.sql",
    "transactions.sql",
    "transaction_items.sql",
    "trades.sql",
    "trade_items.sql",
    "player_week_scores.sql",
]

FANTASY_TEAMS_COLS = [
    "id",
    "season",
    "team_id",
    "owner_id",
    "display_name",
    "team_name",
    "abbrev",
    "active",
]

LEAGUE_SEASONS_COLS = [
    "season",
    "first_scoring_period",
    "latest_scoring_period",
    "transaction_scoring_period",
    "regular_season_end_week",
    "pickup_eval_end_week",
]

TRANSACTIONS_COLS = [
    "transaction_id",
    "related_transaction_id",
    "season",
    "week",
    "transaction_type",
    "status",
    "execution_type",
    "team_id",
    "member_id",
    "bid_amount",
    "proposed_date",
    "accepted_date",
    "process_date",
    "expiration_date",
    "is_pending",
    "raw_json",
]

TRANSACTION_ITEMS_COLS = [
    "id",
    "transaction_id",
    "related_transaction_id",
    "season",
    "week",
    "transaction_type",
    "status",
    "item_type",
    "player_id",
    "from_team_id",
    "to_team_id",
    "from_lineup_slot_id",
    "to_lineup_slot_id",
    "is_keeper",
    "overall_pick_number",
]

TRADES_COLS = [
    "trade_id",
    "related_transaction_id",
    "season",
    "week",
    "accepted_transaction_id",
    "proposal_transaction_id",
    "uphold_transaction_id",
    "team_1_id",
    "team_2_id",
    "proposed_date",
    "accepted_date",
    "process_date",
    "raw_json",
]

TRADE_ITEMS_COLS = [
    "id",
    "trade_id",
    "season",
    "week",
    "player_id",
    "from_team_id",
    "to_team_id",
    "from_lineup_slot_id",
    "to_lineup_slot_id",
    "is_keeper",
    "overall_pick_number",
]

PLAYER_WEEK_SCORES_COLS = [
    "id",
    "season",
    "week",
    "player_id",
    "player_name",
    "position",
    "pro_team",
    "fantasy_team_id",
    "lineup_slot_id",
    "lineup_slot",
    "points",
    "projected_points",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Populate fantasy teams, transaction, trade, and player weekly score tables."
    )
    parser.add_argument("--start-season", type=int, default=2018)
    parser.add_argument("--end-season", type=int, default=const.SEASON)
    parser.add_argument("--league-id", default=const.LEAGUE_ID)
    parser.add_argument(
        "--skip-player-scores",
        action="store_true",
        help="Only update team, transaction, and trade tables.",
    )
    return parser.parse_args()


def upsert_sql(table, cols):
    col_str = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    primary_key = "season" if table == "league_seasons" else "id"
    update_str = ", ".join([f"{col}=VALUES({col})" for col in cols if col != primary_key])
    return f"""
        INSERT INTO {table} ({col_str})
        VALUES ({placeholders})
        ON DUPLICATE KEY UPDATE
        {update_str};
    """


def create_tables(cursor):
    database_dir = Path(__file__).resolve().parents[1]
    for schema_file in SCHEMA_FILES:
        cursor.execute((database_dir / schema_file).read_text())


def get_status(loader):
    return loader.status().get("status", {})


def get_scoring_periods(status):
    first_period = status.get("firstScoringPeriod", 1)
    last_period = status.get("transactionScoringPeriod") or status.get("latestScoringPeriod", 1)
    return range(first_period, last_period + 1)


def pickup_eval_end_week(season):
    return 15 if season <= 2020 else 16


def collect_league_season_row(season, settings_payload, status):
    settings = settings_payload.get("settings", {})
    schedule_settings = settings.get("scheduleSettings", {})
    return {
        "season": season,
        "first_scoring_period": status.get("firstScoringPeriod"),
        "latest_scoring_period": status.get("latestScoringPeriod"),
        "transaction_scoring_period": status.get("transactionScoringPeriod"),
        "regular_season_end_week": schedule_settings.get("matchupPeriodCount"),
        "pickup_eval_end_week": pickup_eval_end_week(season),
    }


def owner_names(owner_id):
    owner = const.TEAM_IDS.get(owner_id, {})
    name = owner.get("name", {})
    return {
        "display": name.get("display", ""),
        "team_name": name.get("team_name", ""),
        "active": owner.get("active"),
    }


def collect_fantasy_team_rows(season, teams_payload):
    rows = []
    for team in teams_payload.get("teams", []):
        owner_id = team.get("primaryOwner", "")
        names = owner_names(owner_id)
        team_id = team.get("id")
        rows.append(
            {
                "id": f"{season}_{team_id}",
                "season": season,
                "team_id": team_id,
                "owner_id": owner_id,
                "display_name": names["display"] or team.get("nickname", ""),
                "team_name": names["team_name"] or team.get("location", ""),
                "abbrev": team.get("abbrev", ""),
                "active": names["active"],
            }
        )
    return rows


def collect_transactions(loader, season, scoring_periods):
    transactions = {}
    for scoring_period in scoring_periods:
        loader.week = scoring_period
        payload = loader.transactions()
        for transaction in payload.get("transactions", []):
            transaction_id = transaction.get("id")
            if transaction_id:
                transactions[transaction_id] = transaction

    return list(transactions.values())


def transaction_row(season, transaction):
    return {
        "transaction_id": transaction.get("id"),
        "related_transaction_id": transaction.get("relatedTransactionId"),
        "season": season,
        "week": transaction.get("scoringPeriodId"),
        "transaction_type": transaction.get("type"),
        "status": transaction.get("status"),
        "execution_type": transaction.get("executionType"),
        "team_id": transaction.get("teamId"),
        "member_id": transaction.get("memberId"),
        "bid_amount": transaction.get("bidAmount", 0),
        "proposed_date": transaction.get("proposedDate"),
        "accepted_date": transaction.get("acceptedDate"),
        "process_date": transaction.get("processDate"),
        "expiration_date": transaction.get("expirationDate"),
        "is_pending": transaction.get("isPending"),
        "raw_json": json.dumps(transaction, sort_keys=True),
    }


def transaction_item_rows(season, transaction):
    rows = []
    transaction_id = transaction.get("id")
    for idx, item in enumerate(transaction.get("items", []), start=1):
        item_type = item.get("type") or transaction.get("type") or "UNKNOWN"
        rows.append(
            {
                "id": f"{transaction_id}_{idx}",
                "transaction_id": transaction_id,
                "related_transaction_id": transaction.get("relatedTransactionId"),
                "season": season,
                "week": transaction.get("scoringPeriodId"),
                "transaction_type": transaction.get("type"),
                "status": transaction.get("status"),
                "item_type": item_type,
                "player_id": item.get("playerId"),
                "from_team_id": item.get("fromTeamId"),
                "to_team_id": item.get("toTeamId"),
                "from_lineup_slot_id": item.get("fromLineupSlotId"),
                "to_lineup_slot_id": item.get("toLineupSlotId"),
                "is_keeper": item.get("isKeeper"),
                "overall_pick_number": item.get("overallPickNumber"),
            }
        )
    return rows


def collect_trade_rows(season, transactions):
    trade_transactions = [
        transaction
        for transaction in transactions
        if "TRADE" in str(transaction.get("type", "")).upper()
    ]
    by_related_id = {}
    for transaction in trade_transactions:
        related_id = transaction.get("relatedTransactionId") or transaction.get("id")
        by_related_id.setdefault(related_id, []).append(transaction)

    trade_rows = []
    trade_item_rows = []
    for related_id, group in by_related_id.items():
        accepted = next(
            (
                transaction
                for transaction in group
                if transaction.get("type") == "TRADE_ACCEPT"
                and transaction.get("status") == "EXECUTED"
                and transaction.get("executionType") == "PROCESS"
                and transaction.get("items")
            ),
            None,
        )
        if not accepted:
            continue

        proposal = next((t for t in group if t.get("type") == "TRADE_PROPOSAL"), None)
        uphold = next((t for t in group if t.get("type") == "TRADE_UPHOLD"), None)
        teams = sorted(
            {
                team_id
                for item in accepted.get("items", [])
                for team_id in (item.get("fromTeamId"), item.get("toTeamId"))
                if team_id
            }
        )
        if len(teams) != 2:
            print(f"  Skipping trade {related_id}: expected 2 teams, found {teams}")
            continue

        trade_id = related_id
        trade_rows.append(
            {
                "trade_id": trade_id,
                "related_transaction_id": related_id,
                "season": season,
                "week": accepted.get("scoringPeriodId"),
                "accepted_transaction_id": accepted.get("id"),
                "proposal_transaction_id": proposal.get("id") if proposal else None,
                "uphold_transaction_id": uphold.get("id") if uphold else None,
                "team_1_id": teams[0],
                "team_2_id": teams[1],
                "proposed_date": accepted.get("proposedDate"),
                "accepted_date": accepted.get("acceptedDate"),
                "process_date": accepted.get("processDate"),
                "raw_json": json.dumps(accepted, sort_keys=True),
            }
        )

        for idx, item in enumerate(accepted.get("items", []), start=1):
            if item.get("type") != "TRADE":
                continue
            trade_item_rows.append(
                {
                    "id": f"{trade_id}_{idx}",
                    "trade_id": trade_id,
                    "season": season,
                    "week": accepted.get("scoringPeriodId"),
                    "player_id": item.get("playerId"),
                    "from_team_id": item.get("fromTeamId"),
                    "to_team_id": item.get("toTeamId"),
                    "from_lineup_slot_id": item.get("fromLineupSlotId"),
                    "to_lineup_slot_id": item.get("toLineupSlotId"),
                    "is_keeper": item.get("isKeeper"),
                    "overall_pick_number": item.get("overallPickNumber"),
                }
            )

    return trade_rows, trade_item_rows


def player_position(player, slotcodes):
    for slot_id in player.get("eligibleSlots", []):
        if slot_id in const.POSITION_MAP:
            return const.POSITION_MAP[slot_id]
    return slotcodes.get(player.get("defaultPositionId"), "")


def player_week_score_rows(loader, season, scoring_periods):
    rows = []
    slotcodes = const.SLOTCODES
    nfl_team_map = const.NFL_TEAM_MAP

    for week in scoring_periods:
        try:
            week_data = loader.load_week(week=week)
        except Exception as exc:
            print(f"  Skipping player scores for season {season}, week {week}: {exc}")
            continue

        for team in week_data.get("teams", []):
            fantasy_team_id = team.get("id")
            for entry in team.get("roster", {}).get("entries", []):
                player = entry.get("playerPoolEntry", {}).get("player", {})
                player_id = entry.get("playerId")
                if not player_id:
                    continue

                points = 0
                projected_points = None
                for stat in player.get("stats", []):
                    if stat.get("scoringPeriodId") != week:
                        continue
                    if stat.get("statSourceId") == 0:
                        points = stat.get("appliedTotal", 0)
                    elif stat.get("statSourceId") == 1:
                        projected_points = stat.get("appliedTotal", 0)

                lineup_slot_id = entry.get("lineupSlotId")
                rows.append(
                    {
                        "id": f"{season}_{week}_{player_id}_{fantasy_team_id}",
                        "season": season,
                        "week": week,
                        "player_id": player_id,
                        "player_name": player.get("fullName"),
                        "position": player_position(player, slotcodes),
                        "pro_team": nfl_team_map.get(player.get("proTeamId")),
                        "fantasy_team_id": fantasy_team_id,
                        "lineup_slot_id": lineup_slot_id,
                        "lineup_slot": slotcodes.get(lineup_slot_id, ""),
                        "points": points,
                        "projected_points": projected_points,
                    }
                )

    return rows


def upsert_rows(cursor, table, cols, rows):
    if not rows:
        return 0

    query = upsert_sql(table, cols)
    for row in rows:
        cursor.execute(query, tuple(row.get(col) for col in cols))
    return len(rows)


def main():
    args = parse_args()
    if not const.SWID or not const.ESPN_S2:
        print("Missing ESPN auth cookies. Check SWID and ESPN_S2 in your .env file.")
        sys.exit(1)
    if not args.league_id:
        print("Missing ESPN league id. Check LEAGUE_ID in your .env file or pass --league-id.")
        sys.exit(1)

    with Database() as conn:
        cursor = conn.cursor()
        create_tables(cursor)

        for season in range(args.start_season, args.end_season + 1):
            print(f"\nProcessing season {season}")
            loader = DataLoader(
                year=season,
                league_id=args.league_id,
                swid=const.SWID,
                espn_s2=const.ESPN_S2,
            )
            status = get_status(loader)
            scoring_periods = list(get_scoring_periods(status))
            settings_payload = loader.settings()
            league_season_rows = [
                collect_league_season_row(season, settings_payload, status)
            ]
            print(
                f"  league_seasons: {upsert_rows(cursor, 'league_seasons', LEAGUE_SEASONS_COLS, league_season_rows)}"
            )

            teams_payload = loader.teams()
            fantasy_team_rows = collect_fantasy_team_rows(season, teams_payload)
            print(
                f"  fantasy_teams: {upsert_rows(cursor, 'fantasy_teams', FANTASY_TEAMS_COLS, fantasy_team_rows)}"
            )

            transactions = collect_transactions(loader, season, scoring_periods)
            transaction_rows = [transaction_row(season, transaction) for transaction in transactions]
            transaction_items = [
                row
                for transaction in transactions
                for row in transaction_item_rows(season, transaction)
            ]
            trade_rows, trade_items = collect_trade_rows(season, transactions)

            print(
                f"  transactions: {upsert_rows(cursor, 'transactions', TRANSACTIONS_COLS, transaction_rows)}"
            )
            print(
                f"  transaction_items: {upsert_rows(cursor, 'transaction_items', TRANSACTION_ITEMS_COLS, transaction_items)}"
            )
            print(f"  trades: {upsert_rows(cursor, 'trades', TRADES_COLS, trade_rows)}")
            print(f"  trade_items: {upsert_rows(cursor, 'trade_items', TRADE_ITEMS_COLS, trade_items)}")

            if not args.skip_player_scores:
                player_rows = player_week_score_rows(loader, season, scoring_periods)
                print(
                    f"  player_week_scores: {upsert_rows(cursor, 'player_week_scores', PLAYER_WEEK_SCORES_COLS, player_rows)}"
                )

            conn.commit()


if __name__ == "__main__":
    main()
