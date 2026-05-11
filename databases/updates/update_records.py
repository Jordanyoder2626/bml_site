from scripts.records.initialize import (
    get_standings_records,
    get_streaks_records,
    get_matchup_records,
    get_tophalf_records
)

from scripts.utils.database import Database
from scripts.utils import constants

import pandas as pd

season = constants.SEASON

# ============================================================
# COLLECT RECORDS
# ============================================================

standings_recs = get_standings_records(season)

longest_streaks = pd.DataFrame(
    get_streaks_records(),
    columns=['category', 'record', 'holder', 'season', 'week']
)

matchup_recs = get_matchup_records(season)
tophalf_recs = get_tophalf_records()

records = pd.concat([
    standings_recs,
    longest_streaks,
    matchup_recs,
    tophalf_recs
], ignore_index=True)

# ============================================================
# CLEAN DATA (CRITICAL FIXES)
# ============================================================

# Replace NaN / empty strings
records = records.fillna('')

# Keep season/week as display strings because tied records can span
# multiple seasons or weeks (for example "2024, 2025").
records['season'] = records['season'].astype(str)
records['week'] = records['week'].astype(str)

# Clamp holder length (fix MySQL 1406 error)
records['holder'] = records['holder'].astype(str).str.slice(0, 100)

# ============================================================
# ADD PRIMARY KEY (SAFE)
# ============================================================

records = records.reset_index(drop=True)
records.insert(0, 'id', range(1, len(records) + 1))

# ============================================================
# DB CONFIG
# ============================================================

records_table = 'records'

records_cols = constants.RECORDS_COLUMNS
if isinstance(records_cols, str):
    records_cols = [c.strip() for c in records_cols.split(",")]

# Make sure column order matches dataframe EXACTLY
records = records[records_cols]

# ============================================================
# UPSERT QUERY (FIX FOR DUPLICATES)
# ============================================================

col_str = ", ".join(records_cols)
placeholders = ", ".join(["%s"] * len(records_cols))

update_str = ", ".join([
    f"{col}=VALUES({col})"
    for col in records_cols if col != "id"
])

query = f"""
INSERT INTO {records_table} ({col_str})
VALUES ({placeholders})
ON DUPLICATE KEY UPDATE
{update_str};
"""

# ============================================================
# EXECUTE
# ============================================================

db = Database()

with db as conn:
    cursor = conn.cursor()

    cursor.execute(f"DELETE FROM {records_table};")

    for _, row in records.iterrows():
        values = tuple(row[col] for col in records_cols)

        cursor.execute(query, values)

    conn.commit()
