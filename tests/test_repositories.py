import pytest
import sqlite3
from unittest.mock import patch, MagicMock

from app.dal.repositories import WordRepository, UserDictionaryRepository
from app.dal.models import CachedWord, Translation, VerbConjugation

@pytest.fixture
def mock_db_connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Create tables for testing
    cursor.execute("""
        CREATE TABLE cached_words (
            word_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hebrew TEXT NOT NULL UNIQUE,
            normalized_hebrew TEXT NOT NULL,
            transcription TEXT,
            is_verb BOOLEAN,
            root TEXT,
            binyan TEXT,
            fetched_at TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE translations (
            translation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER,
            translation_text TEXT NOT NULL,
            context_comment TEXT,
            is_primary BOOLEAN NOT NULL,
            FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE verb_conjugations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER,
            tense TEXT,
            person TEXT,
            hebrew_form TEXT NOT NULL,
            normalized_hebrew_form TEXT NOT NULL,
            transcription TEXT,
            FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE user_dictionary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            word_id INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            srs_level INTEGER DEFAULT 0,
            next_review_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE,
            UNIQUE(user_id, word_id)
        )
    """)
    conn.commit()

    def mock_read_query(query, params=(), fetchone=False, fetchall=False):
        c = conn.cursor()
        c.execute(query, params)
        if fetchone:
            return c.fetchone()
        if fetchall:
            return c.fetchall()
        conn.commit()
        return None

    def mock_write_query(query, params=(), many=False):
        c = conn.cursor()
        if many:
            c.executemany(query, params)
        else:
            c.execute(query, params)
        conn.commit()

    def mock_transaction(func):
        c = conn.cursor()
        result_container = [None]
        try:
            func(c)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e


    with patch('app.dal.repositories.db_read_query', side_effect=mock_read_query):
        with patch('app.dal.repositories.db_write_query', side_effect=mock_write_query):
            with patch('app.dal.repositories.db_transaction', side_effect=mock_transaction):
                yield

    conn.close()


def test_word_repository(mock_db_connection):
    repo = WordRepository()

    # Test create_cached_word
    translations = [{'translation_text': 'to write', 'context_comment': None, 'is_primary': True}]
    conjugations = [{'tense': 'present', 'person': 'm.s.', 'hebrew_form': 'כּוֹתֵב', 'normalized_hebrew_form': 'כותב', 'transcription': 'kotev'}]
    word_id = repo.create_cached_word(
        hebrew='לִכְתּוֹב',
        normalized_hebrew='לכתוב',
        transcription='likhtov',
        is_verb=True,
        root='כ-ת-ב',
        binyan='פעל',
        translations=translations,
        conjugations=conjugations
    )
    assert word_id is not None

    # Test find_word_by_normalized_form
    found_word = repo.find_word_by_normalized_form('לכתוב')
    assert found_word is not None
    assert found_word.hebrew == 'לִכְתּוֹב'
    assert len(found_word.translations) == 1
    assert len(found_word.conjugations) == 1

def test_user_dictionary_repository(mock_db_connection):
    word_repo = WordRepository()
    user_repo = UserDictionaryRepository()

    # Add a word to the cache
    translations = [{'translation_text': 'table', 'context_comment': None, 'is_primary': True}]
    word_id = word_repo.create_cached_word(
        hebrew='שֻׁלְחָן',
        normalized_hebrew='שולחן',
        transcription='shulchan',
        is_verb=False,
        root=None,
        binyan=None,
        translations=translations,
        conjugations=[]
    )

    # Test add_word_to_dictionary
    user_id = 123
    user_repo.add_word_to_dictionary(user_id, word_id)

    # Test is_word_in_dictionary
    assert user_repo.is_word_in_dictionary(user_id, word_id) is True

    # Test get_dictionary_page
    page = user_repo.get_dictionary_page(user_id, 0, 10)
    assert len(page) == 1
    assert page[0]['hebrew'] == 'שֻׁלְחָן'

    # Test remove_word_from_dictionary
    user_repo.remove_word_from_dictionary(user_id, word_id)
    assert user_repo.is_word_in_dictionary(user_id, word_id) is False
