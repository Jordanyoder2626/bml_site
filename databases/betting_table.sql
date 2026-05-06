CREATE TABLE IF NOT EXISTS betting_table (
    id VARCHAR(20) PRIMARY KEY,
    season INT,
    week INT,
    matchup_id INT,
    team VARCHAR(6),
    avg_score DECIMAL(6, 2),
    p_win DECIMAL(4, 4),
    p_tophalf DECIMAL(4, 4),
    p_highest DECIMAL(4, 4),
    p_lowest DECIMAL(4, 4),
    created timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
