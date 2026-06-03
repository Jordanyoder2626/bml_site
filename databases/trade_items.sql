CREATE TABLE IF NOT EXISTS trade_items (
    id VARCHAR(128) PRIMARY KEY,
    trade_id VARCHAR(64) NOT NULL,
    season INT NOT NULL,
    week INT NOT NULL,
    player_id INT NOT NULL,
    from_team_id INT NOT NULL,
    to_team_id INT NOT NULL,
    from_lineup_slot_id INT,
    to_lineup_slot_id INT,
    is_keeper BOOLEAN,
    overall_pick_number INT,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_trade_items_trade (trade_id),
    INDEX idx_trade_items_player (season, player_id),
    INDEX idx_trade_items_from_team (season, from_team_id),
    INDEX idx_trade_items_to_team (season, to_team_id)
);
