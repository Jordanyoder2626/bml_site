Weekly projected team totals and betting odds use the submitted ESPN starters,
including zero or negative scores. Bench and IR scores are excluded. Finished
games use actual points; upcoming games use full projections; active games use
actual points plus a simulated full-game score scaled by the fraction of game
clock remaining. This is a time-based estimate, not a possession or injury model.
Overtime uses the remaining overtime clock. Missing game status stops the update
instead of silently publishing pregame odds.

FantasyPros player projections remain full-game baselines in player_projections;
live adjustments are applied once when calculating betting_table.avg_score and
the associated probabilities. Exact ties split matchup credit and highest/lowest
credit; a median tie receives half credit.

Run from the repository root in your Python environment:

```powershell
python -m unittest scripts.testing.test_live_projections
python -m databases.updates.betting_table --season 2026 --week 1
python -m scripts.export_static
```

Repeat the update and export to refresh during games, then publish docs/ through
the existing publishing workflow. These commands do not install a scheduler or
automatically push the exported site. Season simulations retain their separate
existing forecasting behavior.
