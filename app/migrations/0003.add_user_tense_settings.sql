-- step: 1
-- description: Create user_tense_settings table

CREATE TABLE IF NOT EXISTS user_tense_settings (
    user_id INTEGER NOT NULL,
    tense TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, tense),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);