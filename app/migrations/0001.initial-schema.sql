-- migrations/0001.initial-schema.sql

-- step: apply
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, 
    first_name TEXT, 
    username TEXT
);

CREATE TABLE IF NOT EXISTS cached_words (
    word_id INTEGER PRIMARY KEY AUTOINCREMENT,
    hebrew TEXT NOT NULL UNIQUE,
    normalized_hebrew TEXT NOT NULL,
    transcription TEXT,
    is_verb BOOLEAN,
    root TEXT,
    binyan TEXT,
    fetched_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS translations (
    translation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER,
    translation_text TEXT NOT NULL,
    context_comment TEXT,
    is_primary BOOLEAN NOT NULL,
    FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_dictionary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    word_id INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    srs_level INTEGER DEFAULT 0,
    next_review_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id),
    FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE,
    UNIQUE(user_id, word_id)
);

CREATE TABLE IF NOT EXISTS verb_conjugations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id INTEGER,
    tense TEXT,
    person TEXT,
    hebrew_form TEXT NOT NULL,
    normalized_hebrew_form TEXT NOT NULL,
    transcription TEXT,
    FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE
);

-- Создаем индексы
CREATE INDEX IF NOT EXISTS idx_normalized_hebrew ON cached_words(normalized_hebrew);
CREATE INDEX IF NOT EXISTS idx_normalized_hebrew_form ON verb_conjugations(normalized_hebrew_form);
CREATE INDEX IF NOT EXISTS idx_translations_word_id ON translations(word_id);
