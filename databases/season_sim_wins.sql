CREATE TABLE IF NOT EXISTS season_sim_wins (
    id VARCHAR(20) PRIMARY KEY,
    season INT,
    week INT,
    team VARCHAR(6),
    wins INT,
    p DECIMAL(5, 4),
    created timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
