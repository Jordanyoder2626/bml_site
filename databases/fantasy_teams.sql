CREATE TABLE IF NOT EXISTS fantasy_teams (
    id VARCHAR(32) PRIMARY KEY,
    season INT NOT NULL,
    team_id INT NOT NULL,
    owner_id VARCHAR(64) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    team_name VARCHAR(100),
    abbrev VARCHAR(32),
    active BOOLEAN,
    transaction_losses INT DEFAULT 0,
    transaction_trades INT DEFAULT 0,
    transaction_acquisitions INT DEFAULT 0,
    transaction_drops INT DEFAULT 0,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_fantasy_teams_season_team (season, team_id),
    INDEX idx_fantasy_teams_owner (owner_id),
    INDEX idx_fantasy_teams_display (display_name)
);
