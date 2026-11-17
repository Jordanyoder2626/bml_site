"""Aggregate playoff leverage from paired weekly outcomes and season results."""

import csv
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from scripts.simulations.team_logos import find_team_logo


ROOT = Path(__file__).resolve().parents[2]
COLORS = ('#123d68', '#006b56', '#782f91', '#bb2030', '#a87500',
          '#007e9c', '#d44b16', '#405e35', '#403b86', '#7c405a')


def odds_path(season, week, root=ROOT, metric='playoffs'):
    prefix = 'bootyman' if metric == 'bootyman' else 'playoff'
    return Path(root) / 'www/plots' / f'{prefix}_leverage_{season}_week_{week}.csv'


def build_odds(results, team_names, metric='playoffs'):
    if not results:
        raise ValueError('At least one simulation is required')
    rows = []
    for index, team in enumerate(team_names):
        samples = [result[team] for result in results]
        wins = [sample for sample in samples if sample['current_week_result'] == 1]
        losses = [sample for sample in samples if sample['current_week_result'] == 0]

        def percent(group):
            return 100 * sum(sample[metric] for sample in group) / len(group) if group else None

        rows.append(dict(
            team=team, current=percent(samples), if_loss=percent(losses), if_win=percent(wins),
            color=COLORS[index % len(COLORS)], logo='', simulations=len(samples),
            win_samples=len(wins), loss_samples=len(losses),
        ))
    return rows


def write_odds(results, team_names, season, week, root=ROOT, metric='playoffs'):
    rows = build_odds(results, team_names, metric=metric)
    destination = odds_path(season, week, root, metric=metric)
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc).isoformat()
    for row in rows:
        row.update(season=season, week=week, generated_utc=created)
        logo = find_team_logo(row['team'], root=root)
        if logo:
            row['logo'] = os.path.relpath(logo, destination.parent)
    # Readers see either the complete previous run or the complete new run.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8',
                                         dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            writer = csv.DictWriter(output, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return destination
