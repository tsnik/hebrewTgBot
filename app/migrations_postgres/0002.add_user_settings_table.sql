-- step: 1
-- description: Create user_settings table for general user preferences

CREATE TABLE user_settings (
    user_id BIGINT PRIMARY KEY,
    use_grammatical_forms BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);