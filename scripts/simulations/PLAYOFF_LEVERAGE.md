The playoff leverage chart
=========================

Install the added logo dependencies locally before restarting Flask:

```powershell
python -m pip install "pillow>=11.0" "resvg-py>=0.5.0"
```

Logos are center-cropped into equal-size circles. PNG, JPEG, extensionless images,
and SVGs are supported. Missing paths in existing odds files are resolved from
the team display name at render time, so no simulation rerun is needed for logos.

Generate real BML odds through the normal weekly updater from the project root:

```powershell
python run_updates.py --season 2026 --week 10 --n-sims 10000
```

This runs the existing data/database updates and season simulations using your
configured ESPN and database credentials. `--n-sims` controls both betting and
season simulations. More simulations improve precision, especially for unlikely
weekly outcomes, but take longer. These are estimates under the existing player
projection and season simulation model.

The season updater retains each team's target-week head-to-head result together
with its eventual playoff qualification, using BML's division winners, wildcard
selection and points tiebreakers. Overall odds use every simulated season;
conditional odds use only that team's wins or losses. An unsampled outcome is
blank in the CSV and displayed as N/A. The CSV includes win/loss sample counts,
the simulation count, season, week, and UTC generation time. Top-half results
continue to be simulated, with their existing treatment in the season model.

Output is `www/plots/playoff_leverage_2026_week_10.csv`. Flask automatically
selects the file matching its configured season and current week, so an older
week's odds will not be labeled as current. Restart Flask with matching
`SEASON` and `CURRENT_WEEK` settings and refresh the home page after updating.
The static site exporter includes the rendered chart as well. Without a matching
CSV, the home page shows clearly labeled fictional example data.

The same run also writes `www/plots/bootyman_leverage_2026_week_10.csv` for the
Bootyman Bowl chart directly below the playoff chart. Participation means
finishing among the two worst teams under `order_bootyman_standings` (record,
then points), not losing the Bowl. This chart uses the same simulated seasons,
conditional denominators, and circular logos. Existing odds files need one new
weekly update to populate this additional metric. Until then, that section
shows a message that the odds have not been generated. Static export includes
the second chart whenever its current-week odds file is available.

Aggregation checks (run locally):

```powershell
python -m unittest scripts.testing.test_leverage_odds
```

Preview or custom CSV rendering
-------------------------------

```powershell
python -m scripts.simulations.playoff_leverage scripts/simulations/playoff_leverage.example.csv --season 2026 --week 10
```

This example contains fictional data for checking the design. Output defaults to
`www/plots/playoff_leverage.png`. Use `--output www/plots/playoff_leverage.svg`
for vector export. Change the heading with `--title` and add a methodology footer
with `--note`. Only state a simulation count that actually produced your data.

CSV columns: `team,current,if_loss,if_win,color,logo`. Probabilities use 0 to 100;
leave a conditional probability blank if its outcome was never sampled. Colors
accept Matplotlib names or hex values. An optional local PNG/JPEG logo path is
relative to the CSV directory. Otherwise the team name marks its current odds.
Teams sort by current odds. Automatically generated odds use available nonempty
PNG/JPEG, extensionless, or SVG files named for the team's display name in `logos/`.

The Flask image route `/playoff-leverage.png` renders the chart in memory. No
separate chart-generation command is needed after running the weekly updater.
