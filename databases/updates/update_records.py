from scripts.records.initialize import (
    get_standings_records,
    get_streaks_records,
    get_matchup_records,
    get_tophalf_records,
    get_per_stat_records,
    get_stat_group_records,
    get_most_points_by_position
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
per_stat_recs = get_per_stat_records(season)
stat_group_records = get_stat_group_records(season)
points_by_position = get_most_points_by_position(season)

records = pd.concat([
    standings_recs,
    longest_streaks,
    matchup_recs,
    tophalf_recs,
    per_stat_recs,
    stat_group_records,
    points_by_position
], ignore_index=True)

# ============================================================
# CLEAN DATA (CRITICAL FIXES)
# ============================================================

# Replace NaN / empty strings
records = records.fillna('')

# Ensure correct dtypes
records['season'] = pd.to_numeric(records['season'], errors='coerce').fillna(0).astype(int)
records['week'] = pd.to_numeric(records['week'], errors='coerce').fillna(0).astype(int)

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

    for _, row in records.iterrows():
        values = tuple(row[col] for col in records_cols)

        cursor.execute(query, values)

    conn.commit()