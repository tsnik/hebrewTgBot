-- step: 1
-- description: Create a new cached_words table with an updated schema to support parts of speech and additional word forms. The translations table is not affected.

CREATE TABLE cached_words_new (
    word_id INTEGER PRIMARY KEY AUTOINCREMENT,
    hebrew TEXT NOT NULL,
    normalized_hebrew TEXT NOT NULL,
    transcription TEXT,
    part_of_speech TEXT, -- Replaces is_verb
    root TEXT,
    binyan TEXT,
    gender TEXT,
    singular_form TEXT,
    plural_form TEXT,
    masculine_singular TEXT,
    feminine_singular TEXT,
    masculine_plural TEXT,
    feminine_plural TEXT,
    fetched_at TIMESTAMP,
	UNIQUE(hebrew, part_of_speech) 
);

-- step: 2
-- description: Migrate all existing data from the old cached_words table to the new one.

INSERT INTO cached_words_new (
    word_id, hebrew, normalized_hebrew, transcription, part_of_speech, root, binyan, fetched_at
)
SELECT
    word_id,
    hebrew,
    normalized_hebrew,
    transcription,
    CASE WHEN is_verb = 1 THEN 'verb' ELSE NULL END,
    root,
    binyan,
    fetched_at
FROM cached_words;

-- step: 3
-- description: Remove the old cached_words table.

DROP TABLE cached_words;

-- step: 4
-- description: Rename the new table to its original name.

ALTER TABLE cached_words_new RENAME TO cached_words;
