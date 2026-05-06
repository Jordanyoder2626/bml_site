CREATE TABLE IF NOT EXISTS matchups (
    id VARCHAR(16) PRIMARY KEY,
    season INT,
    week INT,
    team VARCHAR(6),
    score DECIMAL(6, 2),
    opponent VARCHAR(6),
    opponent_score DECIMAL(6, 2),
    matchup_result DECIMAL(2, 1),
    tophalf_result DECIMAL(2, 1),
    created timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
