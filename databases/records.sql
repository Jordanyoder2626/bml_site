CREATE TABLE IF NOT EXISTS records (
    id INT PRIMARY KEY,
    category VARCHAR(100),
    record VARCHAR(100),
    holder VARCHAR(200),
    season VARCHAR(100),
    week VARCHAR(100),
    created timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
