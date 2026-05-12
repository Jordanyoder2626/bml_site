CREATE TABLE IF NOT EXISTS power_ranks (
    id VARCHAR(255) PRIMARY KEY,
    season INT,
    week INT,
    team VARCHAR(255),
    season_idx DECIMAL(5, 4),
    week_idx DECIMAL(5, 4),
    consistency_idx DECIMAL(5, 4),
    luck_idx DECIMAL(5, 4),
    power_score_raw DECIMAL(5, 4),
    power_score_norm DECIMAL(5, 4),
    power_rank INT,
    score_raw_change DECIMAL(5, 4),
    score_norm_change DECIMAL(5, 4),
    rank_change INT,
    created timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
