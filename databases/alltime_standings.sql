CREATE TABLE IF NOT EXISTS alltime_standings (
    id INT PRIMARY KEY,
    team VARCHAR(100),
    seasons INT,
    playoffs INT,
    overall_rec VARCHAR(100),
    win_perc VARCHAR(100),
    matchup_rec VARCHAR(100),
    tophalf_rec VARCHAR(100),
    points VARCHAR(100),
    created timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
