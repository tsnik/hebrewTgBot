import pytest
import sqlite3

from dal.repositories import WordRepository, UserDictionaryRepository
from dal.unit_of_work import UnitOfWork

# It's good practice to enable foreign key constraints for tests to ensure data integrity
DB_PRAGMA = "PRAGMA foreign_keys = ON;"


def get_test_connection(memory_db_uri: str) -> sqlite3.Connection:
    """Helper function to create a connection to the test database."""
    connection = sqlite3.connect(
        memory_db_uri, uri=True, detect_types=sqlite3.PARSE_DECLTYPES
    )
    connection.row_factory = sqlite3.Row  # Allows accessing columns by name
    connection.execute(DB_PRAGMA)
    return connection


def test_word_repository(memory_db):
    """Tests basic WordRepository operations."""
    connection = get_test_connection(memory_db)
    repo = WordRepository(connection)

    # Test data
    translations = [
        {"translation_text": "to write", "context_comment": None, "is_primary": True}
    ]
    conjugations = [
        {
            "tense": "ap",
            "person": "ms",
            "hebrew_form": "כּוֹתֵב",
            "normalized_hebrew_form": "כותב",
            "transcription": "kotev",
        }
    ]

    # 1. Test word creation
    with connection:
        word_id = repo.create_cached_word(
            hebrew="לִכְתּוֹב",
            normalized_hebrew="לכתוב",
            transcription="likhtov",
            is_verb=True,
            root="כ-ת-ב",
            binyan="פעל",
            translations=translations,
            conjugations=conjugations,
        )
    # The 'with' block handles the commit automatically

    assert isinstance(word_id, int)

    # 2. Test finding the word by its normalized form
    found_word = repo.find_word_by_normalized_form("לכתוב")
    assert found_word is not None
    assert found_word.hebrew == "לִכְתּוֹב"
    assert len(found_word.translations) == 1
    assert found_word.translations[0].translation_text == "to write"
    assert len(found_word.conjugations) == 1
    assert found_word.conjugations[0].hebrew_form == "כּוֹתֵב"

    connection.close()


def test_srs_level_management(memory_db):
    """Tests getting and updating the SRS level of a word for a user."""
    connection = get_test_connection(memory_db)
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 101
    srs_level = 5
    next_review_at = "2025-01-01 10:00:00"

    with connection:
        user_repo.add_user(user_id, "SRS", "User")
        translations = [{"translation_text": "to practice", "is_primary": True}]
        word_id = word_repo.create_cached_word(
            hebrew="לְתַרְגֵּל",
            normalized_hebrew="לתרגל",
            transcription="letargel",
            is_verb=True,
            root="ת-ר-ג-ל",
            binyan="פיעל",
            translations=translations,
            conjugations=[],
        )
        user_repo.add_word_to_dictionary(user_id, word_id)
        user_repo.update_srs_level(srs_level, next_review_at, user_id, word_id)

    retrieved_srs_level = user_repo.get_srs_level(user_id, word_id)

    assert retrieved_srs_level is not None
    assert retrieved_srs_level == srs_level

    connection.close()


def test_get_user_words_for_training(memory_db):
    """Tests retrieving user words for training, excluding verbs."""
    connection = get_test_connection(memory_db)
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 789

    with connection:
        user_repo.add_user(user_id, "Train", "User")
        # Add a non-verb word
        translations_noun = [{"translation_text": "book", "is_primary": True}]
        noun_id = word_repo.create_cached_word(
            hebrew="סֵפֶר",
            normalized_hebrew="ספר",
            transcription="sefer",
            is_verb=False,
            part_of_speech="noun",
            root=None,
            binyan=None,
            translations=translations_noun,
            conjugations=[],
        )
        user_repo.add_word_to_dictionary(user_id, noun_id)

        # Add a verb word (should be excluded)
        translations_verb = [{"translation_text": "to read", "is_primary": True}]
        verb_id = word_repo.create_cached_word(
            hebrew="לִקְרוֹא",
            normalized_hebrew="לקרוא",
            transcription="likro",
            is_verb=True,
            root="ק-ר-א",
            binyan="פעל",
            translations=translations_verb,
            conjugations=[],
        )
        user_repo.add_word_to_dictionary(user_id, verb_id)

    training_words = user_repo.get_user_words_for_training(user_id, limit=10)

    assert len(training_words) == 1
    assert training_words[0].word_id == noun_id
    assert training_words[0].part_of_speech == "noun"

    connection.close()


def test_get_random_verb_for_training(memory_db):
    """Tests retrieving a random verb for training."""
    connection = get_test_connection(memory_db)
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 456

    with connection:
        user_repo.add_user(user_id, "Train", "User")
        translations = [{"translation_text": "to learn", "is_primary": True}]
        verb_id = word_repo.create_cached_word(
            hebrew="לִלְמוֹד",
            normalized_hebrew="ללמוד",
            transcription="lilmod",
            is_verb=True,
            root="ל-מ-ד",
            binyan="פעל",
            translations=translations,
            conjugations=[],
        )
        user_repo.add_word_to_dictionary(user_id, verb_id)

    random_verb = word_repo.get_random_verb_for_training(user_id)

    assert random_verb is not None
    assert random_verb.word_id == verb_id
    assert random_verb.part_of_speech == "verb"

    connection.close()


def test_find_words_by_normalized_form(memory_db):
    """Tests finding multiple words by the same normalized form."""
    connection = get_test_connection(memory_db)
    repo = WordRepository(connection)

    # 1. Create multiple words with the same normalized form
    with connection:
        repo.create_cached_word(
            hebrew="בְּדִיקָה",
            normalized_hebrew="בדיקה",
            transcription="bdika",
            is_verb=False,
            root=None,
            binyan=None,
            translations=[{"translation_text": "a check", "is_primary": True}],
            conjugations=[],
        )

    # 2. Find words by the normalized form
    found_words = repo.find_words_by_normalized_form("בדיקה")

    # 3. Assertions
    assert len(found_words) == 1
    assert found_words[0].hebrew == "בְּדִיקָה"

    connection.close()


def test_get_word_by_id(memory_db):
    """Tests fetching a word by its ID."""
    connection = get_test_connection(memory_db)
    repo = WordRepository(connection)

    # 1. Create a word first
    with connection:
        translations = [{"translation_text": "to test", "is_primary": True}]
        word_id = repo.create_cached_word(
            hebrew="לִבְדּוֹק",
            normalized_hebrew="לבדוק",
            transcription="livdok",
            is_verb=True,
            root="ב-ד-ק",
            binyan="פעל",
            translations=translations,
            conjugations=[],
        )

    # 2. Fetch the word by its ID
    found_word = repo.get_word_by_id(word_id)

    # 3. Assertions
    assert found_word is not None
    assert found_word.word_id == word_id
    assert found_word.hebrew == "לִבְדּוֹק"
    assert len(found_word.translations) == 1
    assert found_word.translations[0].translation_text == "to test"

    connection.close()


def test_user_dictionary_repository(memory_db):
    """Тестирует операции со словарём пользователя."""
    connection = get_test_connection(memory_db)
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 123

    # --- Фаза 1: Настройка (Setup) ---
    # Создаём пользователя и слово в одной транзакции
    with connection:
        user_repo.add_user(user_id, "Test", "User")
        translations = [
            {"translation_text": "table", "context_comment": None, "is_primary": True}
        ]
        word_id = word_repo.create_cached_word(
            hebrew="שֻׁלְחָן",
            normalized_hebrew="שולחן",
            transcription="shulchan",
            is_verb=False,
            root=None,
            binyan=None,
            translations=translations,
            conjugations=[],
        )

    # --- Фаза 2: Добавление и проверка ---
    # Добавляем слово в словарь пользователя
    with connection:
        user_repo.add_word_to_dictionary(user_id, word_id)

    # Проверяем, что слово было добавлено
    assert user_repo.is_word_in_dictionary(user_id, word_id) is True

    # Проверяем, что оно появилось на странице словаря
    page = user_repo.get_dictionary_page(user_id, 0, 10)
    assert len(page) == 1
    assert page[0].hebrew == "שֻׁלְחָן"

    # --- Фаза 3: Удаление и проверка ---
    # Удаляем слово
    with connection:
        user_repo.remove_word_from_dictionary(user_id, word_id)

    # Проверяем, что слово было удалено
    assert user_repo.is_word_in_dictionary(user_id, word_id) is False

    # Проверяем, что страница словаря теперь пуста
    page_after_delete = user_repo.get_dictionary_page(user_id, 0, 10)
    assert len(page_after_delete) == 0

    connection.close()


def test_word_repository_transaction_rollback(memory_db):
    """
    Tests that a transaction is rolled back when an error occurs.
    """
    connection = get_test_connection(memory_db)
    repo = WordRepository(connection)

    translations = [{"translation_text": "to fail", "is_primary": True}]
    # Invalid data that will cause a TypeError inside the method
    invalid_conjugations = [1, 2, 3]

    # **THE FIX:** Use 'with connection' to ensure the transaction is rolled back on error.
    with pytest.raises(TypeError):
        with UnitOfWork() as uow:
            uow.words.create_cached_word(
                hebrew="לְהִכָּשֵׁל",
                normalized_hebrew="להכשל",
                transcription="lehikashel",
                is_verb=True,
                root="כ-ש-ל",
                binyan="נפעל",
                translations=translations,
                conjugations=invalid_conjugations,
            )

    # After the exception and automatic rollback, the word should not exist in the database.
    found_word = repo.find_word_by_normalized_form("להכשל")
    assert (
        found_word is None
    ), "Word should not have been created due to transaction rollback."

    connection.close()
