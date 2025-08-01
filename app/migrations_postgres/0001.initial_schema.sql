-- step: 1
-- description: Initial PostgreSQL schema

CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    first_name TEXT,
    username TEXT
);

CREATE TABLE cached_words (
    word_id SERIAL PRIMARY KEY,
    hebrew TEXT NOT NULL,
    normalized_hebrew TEXT NOT NULL,
    transcription TEXT,
    part_of_speech TEXT,
    root TEXT,
    binyan TEXT,
    gender TEXT,
    singular_form TEXT,
    plural_form TEXT,
    masculine_singular TEXT,
    feminine_singular TEXT,
    masculine_plural TEXT,
    feminine_plural TEXT,
    fetched_at TIMESTAMPTZ,
    UNIQUE(hebrew, part_of_speech)
);

CREATE TABLE translations (
    translation_id SERIAL PRIMARY KEY,
    word_id INTEGER NOT NULL,
    translation_text TEXT NOT NULL,
    context_comment TEXT,
    is_primary BOOLEAN NOT NULL,
    FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE
);

CREATE TABLE user_dictionary (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    word_id INTEGER NOT NULL,
    added_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    srs_level INTEGER DEFAULT 0,
    next_review_at TIMESTAMPTZ,
    FOREIGN KEY (user_id) REFERENCES users (user_id),
    FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE,
    UNIQUE(user_id, word_id)
);

CREATE TABLE verb_conjugations (
    id SERIAL PRIMARY KEY,
    word_id INTEGER NOT NULL,
    tense TEXT,
    person TEXT,
    hebrew_form TEXT NOT NULL,
    normalized_hebrew_form TEXT NOT NULL,
    transcription TEXT,
    FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE
);

CREATE TABLE user_tense_settings (
    user_id BIGINT NOT NULL,
    tense TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (user_id, tense),
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
);

-- Индексы
CREATE INDEX idx_normalized_hebrew ON cached_words(normalized_hebrew);
CREATE INDEX idx_normalized_hebrew_form ON verb_conjugations(normalized_hebrew_form);
CREATE INDEX idx_translations_word_id ON translations(word_id);