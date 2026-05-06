CREATE TABLE IF NOT EXISTS standings (
    id VARCHAR(255) PRIMARY KEY,
    m_wins DECIMAL(4, 1),
    m_losses DECIMAL(4, 1),
    th_wins DECIMAL(4, 1),
    th_losses DECIMAL(4, 1),
    total_pf DECIMAL(6, 2),
    created timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
