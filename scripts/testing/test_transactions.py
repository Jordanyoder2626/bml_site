import argparse
import json
import os
import sys

import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from scripts.api.DataLoader import DataLoader
from scripts.utils import constants as const


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test whether ESPN returns transaction data for the configured league."
    )
    parser.add_argument(
        "--season",
        type=int,
        default=const.SEASON,
        help="ESPN season to query. Defaults to the project season constant.",
    )
    parser.add_argument(
        "--league-id",
        default=const.LEAGUE_ID,
        help="ESPN league id. Defaults to the project league constant.",
    )
    parser.add_argument(
        "--week",
        type=int,
        default=None,
        help="Optional scoring period to query. Defaults to checking every scoring period.",
    )
    parser.add_argument(
        "--types",
        default="FREEAGENT,WAIVER,WAIVER_ERROR,TRADE",
        help="Comma-separated ESPN transaction types to request.",
    )
    return parser.parse_args()


def extract_transactions(payload):
    if isinstance(payload, list):
        return payload, "list"

    if isinstance(payload, dict):
        for key in ("transactions", "transactionSegments", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value, key

    return [], type(payload).__name__


def fetch_league_status(args, swid, espn_s2, league_id):
    url = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/"
        f"{args.season}/segments/0/leagues/{league_id}"
    )
    response = requests.get(
        url,
        params={"view": "mStatus"},
        cookies={"SWID": swid, "espn_s2": espn_s2},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("status", {})


def fetch_transactions(args, swid, espn_s2, league_id, scoring_period, transaction_types):
    url = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/"
        f"{args.season}/segments/0/leagues/{league_id}"
    )
    params = {
        "view": "mTransactions2",
        "scoringPeriodId": scoring_period,
    }
    filters = {
        "transactions": {
            "filterType": {
                "value": transaction_types,
            }
        }
    }

    response = requests.get(
        url,
        params=params,
        cookies={"SWID": swid, "espn_s2": espn_s2},
        headers={"x-fantasy-filter": json.dumps(filters)},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_transactions_without_type_filter(args, swid, espn_s2, league_id, scoring_period):
    url = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/"
        f"{args.season}/segments/0/leagues/{league_id}"
    )
    response = requests.get(
        url,
        params={
            "view": "mTransactions2",
            "scoringPeriodId": scoring_period,
        },
        cookies={"SWID": swid, "espn_s2": espn_s2},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_transaction_activity(args, swid, espn_s2, league_id):
    base_urls = [
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons",
        "https://lm-api-communication.fantasy.espn.com/apis/v3/games/ffl/seasons",
        "https://fantasy.espn.com/apis/v3/games/ffl/seasons",
    ]
    urls = []
    for base_url in base_urls:
        season_url = f"{base_url}/{args.season}"
        urls.extend(
            [
                f"{season_url}/segments/0/leagues/{league_id}/communication",
                f"{season_url}/segments/0/leagues/{league_id}/communication/",
            ]
        )
    views = [
        "kona_league_communication",
        "kona_league_messageboard",
    ]
    filters = {
        "topics": {
            "filterType": {
                "value": ["ACTIVITY_TRANSACTIONS"],
            },
            "filterIncludeMessageTypeIds": {
                "value": [178, 179, 180, 181, 239, 244],
            },
            "limit": 100,
            "limitPerMessageSet": {
                "value": 25,
            },
            "offset": 0,
            "sortFor": {
                "sortPriority": 2,
                "sortAsc": False,
            },
            "sortMessageDate": {
                "sortPriority": 1,
                "sortAsc": False,
            },
        }
    }
    errors = []
    for url in urls:
        for view in views:
            response = requests.get(
                url,
                params={"view": view},
                cookies={"SWID": swid, "espn_s2": espn_s2},
                headers={"x-fantasy-filter": json.dumps(filters)},
                timeout=30,
            )
            if response.ok:
                payload = response.json()
                if isinstance(payload, dict):
                    payload["_activityRequestUrl"] = response.url
                return payload
            errors.append(f"{response.status_code}: {response.url}")

    raise RuntimeError(f"All transaction activity requests failed: {errors}")


def fetch_league_communication_view(args, swid, espn_s2, league_id):
    url = (
        "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/"
        f"{args.season}/segments/0/leagues/{league_id}"
    )
    filters = {
        "topics": {
            "filterType": {
                "value": ["ACTIVITY_TRANSACTIONS"],
            },
            "filterIncludeMessageTypeIds": {
                "value": [178, 179, 180, 181, 239, 244],
            },
            "limit": 100,
            "limitPerMessageSet": {
                "value": 25,
            },
            "offset": 0,
            "sortFor": {
                "sortPriority": 2,
                "sortAsc": False,
            },
            "sortMessageDate": {
                "sortPriority": 1,
                "sortAsc": False,
            },
        }
    }
    response = requests.get(
        url,
        params={"view": "kona_league_communication"},
        cookies={"SWID": swid, "espn_s2": espn_s2},
        headers={"x-fantasy-filter": json.dumps(filters)},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        payload["_activityRequestUrl"] = response.url
    return payload


def transaction_type_attempts(transaction_types):
    attempts = [transaction_types]
    pickup_types = [
        txn_type
        for txn_type in transaction_types
        if txn_type in ("FREEAGENT", "WAIVER", "WAIVER_ERROR")
    ]
    if pickup_types and pickup_types not in attempts:
        attempts.append(pickup_types)

    for txn_type in transaction_types:
        single_type = [txn_type]
        if single_type not in attempts:
            attempts.append(single_type)

    return attempts


def collect_unfiltered_transactions(args, swid, espn_s2, league_id, scoring_periods):
    transactions = []
    failed_requests = []
    last_payload = None

    for scoring_period in scoring_periods:
        try:
            last_payload = fetch_transactions_without_type_filter(
                args,
                swid,
                espn_s2,
                league_id,
                scoring_period,
            )
        except Exception as exc:
            failed_requests.append(
                {
                    "scoringPeriodId": scoring_period,
                    "error": str(exc),
                }
            )
            continue

        period_transactions, source_key = extract_transactions(last_payload)
        for transaction in period_transactions:
            if isinstance(transaction, dict):
                transaction["_scoringPeriodIdQueried"] = scoring_period
                transaction["_transactionContainer"] = source_key
        transactions.extend(period_transactions)

    return transactions, failed_requests, last_payload


def print_trade_type_examples(transactions):
    trade_transactions = [
        transaction
        for transaction in transactions
        if isinstance(transaction, dict)
        and "TRADE" in str(transaction.get("type", "")).upper()
    ]
    if not trade_transactions:
        return

    print("\nTrade transaction status/type counts:")
    counts = {}
    for transaction in trade_transactions:
        key = (
            transaction.get("type") or "",
            transaction.get("status") or "",
            transaction.get("executionType") or "",
        )
        counts[key] = counts.get(key, 0) + 1

    for key, count in sorted(counts.items()):
        print(f"{key}: {count}")

    preferred_examples = [
        ("TRADE_UPHOLD", "EXECUTED"),
        ("TRADE_ACCEPT", "EXECUTED"),
        ("TRADE_PROPOSAL", "EXECUTED"),
    ]
    printed_ids = set()
    for trade_type, status in preferred_examples:
        example = next(
            (
                transaction
                for transaction in trade_transactions
                if transaction.get("type") == trade_type
                and transaction.get("status") == status
            ),
            None,
        )
        if example:
            printed_ids.add(example.get("id"))
            print(f"\nExample {trade_type} / {status} transaction JSON:")
            print(json.dumps(example, indent=2, sort_keys=True, default=str))

    if not printed_ids:
        print("\nNo executed trade examples found. Printing first trade-like transaction:")
        print(json.dumps(trade_transactions[0], indent=2, sort_keys=True, default=str))


def print_completed_trade_group_examples(transactions):
    trade_transactions = [
        transaction
        for transaction in transactions
        if isinstance(transaction, dict)
        and "TRADE" in str(transaction.get("type", "")).upper()
    ]
    completed_accepts = [
        transaction
        for transaction in trade_transactions
        if transaction.get("type") == "TRADE_ACCEPT"
        and transaction.get("status") == "EXECUTED"
        and transaction.get("items")
    ]
    if not completed_accepts:
        print("\nNo completed trade accept rows with player items found.")
        return

    example_accept = completed_accepts[0]
    related_id = example_accept.get("relatedTransactionId")
    trade_group = [
        transaction
        for transaction in trade_transactions
        if transaction.get("relatedTransactionId") == related_id
        or transaction.get("id") == related_id
        or transaction.get("id") == example_accept.get("id")
    ]
    trade_group = sorted(
        trade_group,
        key=lambda transaction: (
            transaction.get("proposedDate") or 0,
            transaction.get("processDate") or 0,
            transaction.get("type") or "",
        ),
    )

    print("\nCompleted trade group summary:")
    print(f"relatedTransactionId: {related_id}")
    for transaction in trade_group:
        print(
            {
                "id": transaction.get("id"),
                "type": transaction.get("type"),
                "status": transaction.get("status"),
                "executionType": transaction.get("executionType"),
                "teamId": transaction.get("teamId"),
                "scoringPeriodId": transaction.get("scoringPeriodId"),
                "items": len(transaction.get("items", [])),
            }
        )

    print("\nCompleted trade accept row to parse into trade_items:")
    print(json.dumps(example_accept, indent=2, sort_keys=True, default=str))


def print_transaction_activity_sample(args, swid, espn_s2, league_id):
    print("\nChecking transaction activity feed for add/drop/trade messages...")
    try:
        activity_payload = fetch_transaction_activity(args, swid, espn_s2, league_id)
    except Exception as exc:
        print(f"Transaction activity request failed: {exc}")
        print("\nTrying league communication view on the normal league endpoint...")
        try:
            activity_payload = fetch_league_communication_view(args, swid, espn_s2, league_id)
        except Exception as fallback_exc:
            print(f"League communication view request failed: {fallback_exc}")
            return

    topics = activity_payload.get("topics", [])
    if not topics and isinstance(activity_payload.get("topicsByType"), dict):
        topics = [
            topic
            for topic_list in activity_payload["topicsByType"].values()
            for topic in topic_list
        ]
    print(f"Transaction activity count: {len(topics)}")
    if not topics:
        print("No transaction activity returned.")
        print("\nRaw transaction activity response JSON:")
        print(json.dumps(activity_payload, indent=2, sort_keys=True, default=str))
        return

    print("\nExample transaction activity JSON:")
    print(json.dumps(topics[0], indent=2, sort_keys=True, default=str))


def main():
    args = parse_args()
    swid = const.SWID
    espn_s2 = const.ESPN_S2
    league_id = args.league_id

    if not swid or not espn_s2:
        print("Missing ESPN auth cookies. Check SWID and ESPN_S2 in your .env file.")
        sys.exit(1)
    if not league_id:
        print("Missing ESPN league id. Check LEAGUE_ID in your .env file or pass --league-id.")
        sys.exit(1)

    transaction_types = [
        txn_type.strip()
        for txn_type in args.types.split(",")
        if txn_type.strip()
    ]
    status = fetch_league_status(args, swid, espn_s2, league_id)
    first_period = status.get("firstScoringPeriod", 1)
    last_period = status.get("transactionScoringPeriod") or status.get("latestScoringPeriod", 1)
    scoring_periods = [args.week] if args.week else range(first_period, last_period + 1)

    all_transactions = []
    failed_requests = []
    successful_type_attempt = None
    last_payload = None
    scoring_periods_checked = list(scoring_periods)

    for type_attempt in transaction_type_attempts(transaction_types):
        all_transactions = []
        failed_requests = []
        for scoring_period in scoring_periods_checked:
            try:
                last_payload = fetch_transactions(
                    args,
                    swid,
                    espn_s2,
                    league_id,
                    scoring_period,
                    type_attempt,
                )
            except Exception as exc:
                failed_requests.append(
                    {
                        "scoringPeriodId": scoring_period,
                        "types": type_attempt,
                        "error": str(exc),
                    }
                )
                continue

            transactions, source_key = extract_transactions(last_payload)
            for transaction in transactions:
                if isinstance(transaction, dict):
                    transaction["_scoringPeriodIdQueried"] = scoring_period
                    transaction["_transactionContainer"] = source_key
            all_transactions.extend(transactions)

        if all_transactions:
            successful_type_attempt = type_attempt
            break

    print(f"Requested transaction types: {transaction_types}")
    print(f"Successful transaction type request: {successful_type_attempt}")
    print(f"Scoring periods checked: {scoring_periods_checked}")
    if failed_requests:
        print(f"Last failed request set: {failed_requests}")
    print(f"Transaction count: {len(all_transactions)}")
    if all_transactions:
        transaction_types_found = sorted(
            {
                transaction.get("type")
                for transaction in all_transactions
                if isinstance(transaction, dict) and transaction.get("type")
            }
        )
        print(f"Filtered transaction types found: {transaction_types_found}")

    print("\nChecking unfiltered mTransactions2 results...")
    unfiltered_transactions, unfiltered_failures, unfiltered_payload = collect_unfiltered_transactions(
        args,
        swid,
        espn_s2,
        league_id,
        scoring_periods_checked,
    )
    print(f"Unfiltered transaction count: {len(unfiltered_transactions)}")
    if unfiltered_failures:
        print(f"Unfiltered failed requests: {unfiltered_failures}")
    unfiltered_types_found = sorted(
        {
            transaction.get("type")
            for transaction in unfiltered_transactions
            if isinstance(transaction, dict) and transaction.get("type")
        }
    )
    print(f"Unfiltered transaction types found: {unfiltered_types_found}")
    trade_like_transactions = [
        transaction
        for transaction in unfiltered_transactions
        if isinstance(transaction, dict)
        and "TRADE" in str(transaction.get("type", "")).upper()
    ]
    print(f"Unfiltered trade-like transaction count: {len(trade_like_transactions)}")
    if trade_like_transactions:
        print("\nExample trade-like transaction JSON:")
        print(json.dumps(trade_like_transactions[0], indent=2, sort_keys=True, default=str))
    print_trade_type_examples(unfiltered_transactions)
    print_completed_trade_group_examples(unfiltered_transactions)

    if not all_transactions:
        print("No transactions returned.")
        if unfiltered_payload is not None:
            print("\nLast unfiltered raw response JSON:")
            print(json.dumps(unfiltered_payload, indent=2, sort_keys=True, default=str))
        elif last_payload is not None:
            print("\nLast raw response JSON:")
            print(json.dumps(last_payload, indent=2, sort_keys=True, default=str))

        print_transaction_activity_sample(args, swid, espn_s2, league_id)

        print("\nTrying the project's DataLoader.transactions() fallback...")
        loader = DataLoader(
            year=args.season,
            league_id=league_id,
            swid=swid,
            espn_s2=espn_s2,
            week=args.week,
        )
        fallback_payload = loader.transactions()
        print(json.dumps(fallback_payload, indent=2, sort_keys=True, default=str))
        return

    print("\nExample transaction JSON:")
    print(json.dumps(all_transactions[0], indent=2, sort_keys=True, default=str))
    print_transaction_activity_sample(args, swid, espn_s2, league_id)


if __name__ == "__main__":
    main()
