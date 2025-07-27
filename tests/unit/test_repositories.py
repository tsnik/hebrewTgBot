import pytest
import sqlite3
from datetime import datetime

from dal.repositories import WordRepository, UserDictionaryRepository

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
            "tense": "present",
            "person": "m.s.",
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
    assert page[0]["hebrew"] == "שֻׁלְחָן"

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
        with connection:
            repo.create_cached_word(
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
