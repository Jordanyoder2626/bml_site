CREATE TABLE IF NOT EXISTS efficiency (
    id VARCHAR(16) PRIMARY KEY,
    season INT,
    week INT,
    team VARCHAR(8),
    actual_lineup_score FLOAT(6, 2),
    actual_lineup_projected FLOAT(6, 2),
    best_projected_lineup_score FLOAT(6, 2),
    best_projected_lineup_projected FLOAT(6, 2),
    optimal_lineup_score FLOAT(6, 2),
    optimal_lineup_projected FLOAT(6, 2),
    created timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
