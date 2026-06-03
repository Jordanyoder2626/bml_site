CREATE TABLE IF NOT EXISTS league_seasons (
    season INT PRIMARY KEY,
    first_scoring_period INT,
    latest_scoring_period INT,
    transaction_scoring_period INT,
    regular_season_end_week INT,
    pickup_eval_end_week INT,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
