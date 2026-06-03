import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from scripts.api.DataLoader import DataLoader
from scripts.utils import constants as const


def parse_args():
    parser = argparse.ArgumentParser(
        description="Print ESPN numeric team IDs and owner IDs by season."
    )
    parser.add_argument(
        "--start-season",
        type=int,
        default=2018,
        help="First season to query.",
    )
    parser.add_argument(
        "--end-season",
        type=int,
        default=const.SEASON,
        help="Last season to query.",
    )
    parser.add_argument(
        "--league-id",
        default=const.LEAGUE_ID,
        help="ESPN league id. Defaults to the project league constant.",
    )
    return parser.parse_args()


def team_display_from_constants(owner_id):
    owner = const.TEAM_IDS.get(owner_id)
    if not owner:
        return "", "", None

    name = owner.get("name", {})
    return (
        name.get("display", ""),
        name.get("team_name", ""),
        owner.get("active"),
    )


def main():
    args = parse_args()

    if not const.SWID or not const.ESPN_S2:
        print("Missing ESPN auth cookies. Check SWID and ESPN_S2 in your .env file.")
        sys.exit(1)
    if not args.league_id:
        print("Missing ESPN league id. Check LEAGUE_ID in your .env file or pass --league-id.")
        sys.exit(1)

    print(
        "season,team_id,primary_owner,constant_display,constant_team_name,"
        "constant_active,espn_location,espn_nickname,espn_abbrev"
    )

    for season in range(args.start_season, args.end_season + 1):
        loader = DataLoader(
            year=season,
            league_id=args.league_id,
            swid=const.SWID,
            espn_s2=const.ESPN_S2,
        )
        payload = loader.teams()
        for team in payload.get("teams", []):
            owner_id = team.get("primaryOwner", "")
            display, team_name, active = team_display_from_constants(owner_id)
            print(
                ",".join(
                    [
                        str(season),
                        str(team.get("id", "")),
                        owner_id,
                        display,
                        team_name,
                        "" if active is None else str(active),
                        str(team.get("location", "")),
                        str(team.get("nickname", "")),
                        str(team.get("abbrev", "")),
                    ]
                )
            )


if __name__ == "__main__":
    main()
