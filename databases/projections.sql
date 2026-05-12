CREATE TABLE IF NOT EXISTS player_projections (
    id VARCHAR(255) PRIMARY KEY,
    season INT,
    week INT,
    name VARCHAR(225),
    espn_id INT,
    position VARCHAR(255),
    receptions FLOAT,
    projection FLOAT,
    created timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
