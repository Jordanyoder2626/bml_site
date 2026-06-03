CREATE TABLE IF NOT EXISTS player_week_scores (
    id VARCHAR(64) PRIMARY KEY,
    season INT NOT NULL,
    week INT NOT NULL,
    player_id INT NOT NULL,
    player_name VARCHAR(255),
    position VARCHAR(16),
    pro_team VARCHAR(16),
    fantasy_team_id INT,
    lineup_slot_id INT,
    lineup_slot VARCHAR(16),
    points DECIMAL(7, 2) DEFAULT 0,
    projected_points DECIMAL(7, 2),
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_player_week_team (season, week, player_id, fantasy_team_id),
    INDEX idx_player_week_scores_player (season, player_id, week),
    INDEX idx_player_week_scores_team (season, fantasy_team_id, week),
    INDEX idx_player_week_scores_points (season, points)
);
