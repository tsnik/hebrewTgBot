import pytest
import sqlite3
from datetime import datetime

# Импортируем Pydantic-модели для создания данных
from dal.models import (
    CreateCachedWord,
    CreateTranslation,
    CreateVerbConjugation,
    PartOfSpeech,
    Tense,
    Person,
    Binyan,
)
from dal.repositories import WordRepository, UserDictionaryRepository
from dal.unit_of_work import UnitOfWork

# Прагма для обеспечения целостности данных в тестах
DB_PRAGMA = "PRAGMA foreign_keys = ON;"


def get_test_connection(memory_db_uri: str) -> sqlite3.Connection:
    """Вспомогательная функция для создания подключения к тестовой БД."""
    connection = sqlite3.connect(
        memory_db_uri, uri=True, detect_types=sqlite3.PARSE_DECLTYPES
    )
    connection.row_factory = sqlite3.Row
    connection.execute(DB_PRAGMA)
    return connection


def test_word_repository(memory_db):
    """Тестирует базовые операции WordRepository с новыми моделями."""
    connection = get_test_connection(memory_db)
    repo = WordRepository(connection)

    # 1. Готовим данные с использованием типизированных моделей
    translations = [
        CreateTranslation(
            translation_text="to write", context_comment=None, is_primary=True
        )
    ]
    conjugations = [
        CreateVerbConjugation(
            tense=Tense.PRESENT,
            person=Person.MS,
            hebrew_form="כּוֹתֵב",
            normalized_hebrew_form="כותב",
            transcription="kotev",
        )
    ]

    word_to_create = CreateCachedWord(
        hebrew="לִכְתּוֹב",
        normalized_hebrew="לכתוב",
        transcription="likhtov",
        part_of_speech=PartOfSpeech.VERB,
        root="כ-ת-ב",
        binyan=Binyan.PAAL,
        translations=translations,
        conjugations=conjugations,
    )

    # 2. Тестируем создание слова, передавая один объект
    with connection:
        word_id = repo.create_cached_word(word_to_create)

    assert isinstance(word_id, int)

    # 3. Тестируем поиск слова
    found_word = repo.find_words_by_normalized_form("לכתוב")[0]
    assert found_word is not None
    assert found_word.hebrew == "לִכְתּוֹב"
    assert len(found_word.translations) == 1
    assert found_word.translations[0].translation_text == "to write"
    assert len(found_word.conjugations) == 1
    assert found_word.conjugations[0].hebrew_form == "כּוֹתֵב"

    connection.close()


def test_srs_level_management(memory_db):
    """Тестирует управление SRS-уровнем слова."""
    connection = get_test_connection(memory_db)
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 101
    srs_level = 5
    next_review_at = datetime(2025, 1, 1, 10, 0, 0)

    with connection:
        user_repo.add_user(user_id, "SRS", "User")
        word_to_create = CreateCachedWord(
            hebrew="לְתַרְגֵּל",
            normalized_hebrew="לתרגל",
            transcription="letargel",
            part_of_speech=PartOfSpeech.VERB,
            root="ת-ר-ג-ל",
            binyan=Binyan.PIEL,
            translations=[
                CreateTranslation(translation_text="to practice", is_primary=True)
            ],
        )
        word_id = word_repo.create_cached_word(word_to_create)
        user_repo.add_word_to_dictionary(user_id, word_id)
        user_repo.update_srs_level(srs_level, next_review_at, user_id, word_id)

    retrieved_srs_level = user_repo.get_srs_level(user_id, word_id)

    assert retrieved_srs_level is not None
    assert retrieved_srs_level == srs_level

    connection.close()


def test_get_user_words_for_training(memory_db):
    """Тестирует получение слов для тренировки (глаголы должны быть исключены)."""
    connection = get_test_connection(memory_db)
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 789

    with connection:
        user_repo.add_user(user_id, "Train", "User")

        # Добавляем существительное
        noun_to_create = CreateCachedWord(
            hebrew="סֵפֶר",
            normalized_hebrew="ספר",
            transcription="sefer",
            part_of_speech=PartOfSpeech.NOUN,
            translations=[CreateTranslation(translation_text="book", is_primary=True)],
        )
        noun_id = word_repo.create_cached_word(noun_to_create)
        user_repo.add_word_to_dictionary(user_id, noun_id)

        # Добавляем глагол (должен быть исключен)
        verb_to_create = CreateCachedWord(
            hebrew="לִקְרוֹא",
            normalized_hebrew="לקרוא",
            transcription="likro",
            part_of_speech=PartOfSpeech.VERB,
            root="ק-ר-א",
            binyan=Binyan.PAAL,
            translations=[
                CreateTranslation(translation_text="to read", is_primary=True)
            ],
        )
        verb_id = word_repo.create_cached_word(verb_to_create)
        user_repo.add_word_to_dictionary(user_id, verb_id)

    training_words = user_repo.get_user_words_for_training(user_id, limit=10)

    assert len(training_words) == 1
    assert training_words[0].word_id == noun_id
    assert training_words[0].part_of_speech == "noun"

    connection.close()


def test_get_random_verb_for_training(memory_db):
    """Тестирует получение случайного глагола для тренировки."""
    connection = get_test_connection(memory_db)
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 456

    with connection:
        user_repo.add_user(user_id, "Train", "User")
        verb_to_create = CreateCachedWord(
            hebrew="לִלְמוֹד",
            normalized_hebrew="ללמוד",
            transcription="lilmod",
            part_of_speech=PartOfSpeech.VERB,
            root="ל-מ-ד",
            binyan=Binyan.PAAL,
            translations=[
                CreateTranslation(translation_text="to learn", is_primary=True)
            ],
        )
        verb_id = word_repo.create_cached_word(verb_to_create)
        user_repo.add_word_to_dictionary(user_id, verb_id)

    random_verb = word_repo.get_random_verb_for_training(user_id)

    assert random_verb is not None
    assert random_verb.word_id == verb_id
    assert random_verb.part_of_speech == "verb"

    connection.close()


def test_find_words_by_normalized_form(memory_db):
    """Тестирует поиск слов по нормализованной форме."""
    connection = get_test_connection(memory_db)
    repo = WordRepository(connection)

    with connection:
        word_to_create = CreateCachedWord(
            hebrew="בְּדִיקָה",
            normalized_hebrew="בדיקה",
            transcription="bdika",
            part_of_speech=PartOfSpeech.NOUN,
            translations=[
                CreateTranslation(translation_text="a check", is_primary=True)
            ],
        )
        repo.create_cached_word(word_to_create)

    found_words = repo.find_words_by_normalized_form("בדיקה")

    assert len(found_words) == 1
    assert found_words[0].hebrew == "בְּדִיקָה"

    connection.close()


def test_get_word_by_id(memory_db):
    """Тестирует получение слова по его ID."""
    connection = get_test_connection(memory_db)
    repo = WordRepository(connection)

    with connection:
        word_to_create = CreateCachedWord(
            hebrew="לִבְדּוֹק",
            normalized_hebrew="לבדוק",
            transcription="livdok",
            part_of_speech=PartOfSpeech.VERB,
            root="ב-ד-ק",
            binyan=Binyan.PAAL,
            translations=[
                CreateTranslation(translation_text="to test", is_primary=True)
            ],
        )
        word_id = repo.create_cached_word(word_to_create)

    found_word = repo.get_word_by_id(word_id)

    assert found_word is not None
    assert found_word.word_id == word_id
    assert found_word.hebrew == "לִבְדּוֹק"
    assert len(found_word.translations) == 1
    assert found_word.translations[0].translation_text == "to test"

    connection.close()


def test_user_dictionary_repository(memory_db):
    """Тестирует полный цикл операций со словарём пользователя."""
    connection = get_test_connection(memory_db)
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 123

    with connection:
        user_repo.add_user(user_id, "Test", "User")
        word_to_create = CreateCachedWord(
            hebrew="שֻׁלְחָן",
            normalized_hebrew="שולחן",
            transcription="shulchan",
            part_of_speech=PartOfSpeech.NOUN,
            translations=[CreateTranslation(translation_text="table", is_primary=True)],
        )
        word_id = word_repo.create_cached_word(word_to_create)

    with connection:
        user_repo.add_word_to_dictionary(user_id, word_id)

    assert user_repo.is_word_in_dictionary(user_id, word_id) is True
    page = user_repo.get_dictionary_page(user_id, 0, 10)
    assert len(page) == 1
    assert page[0].hebrew == "שֻׁלְחָן"

    with connection:
        user_repo.remove_word_from_dictionary(user_id, word_id)

    assert user_repo.is_word_in_dictionary(user_id, word_id) is False
    page_after_delete = user_repo.get_dictionary_page(user_id, 0, 10)
    assert len(page_after_delete) == 0

    connection.close()


def test_word_repository_transaction_rollback(memory_db):
    """Тестирует, что транзакция откатывается при ошибке."""
    connection = get_test_connection(memory_db)
    repo = WordRepository(connection)

    # Создаем заведомо невалидные данные (неправильный тип в списке)
    invalid_translations = [1, 2, 3]

    with pytest.raises(Exception):  # Ловим любую ошибку (Pydantic или TypeError)
        with UnitOfWork() as uow:
            # Пытаемся создать модель с невалидными данными
            word_to_create = CreateCachedWord(
                hebrew="לְהִכָּשֵׁל",
                normalized_hebrew="להכשל",
                transcription="lehikashel",
                part_of_speech=PartOfSpeech.VERB,
                translations=invalid_translations,  # Невалидные данные
            )
            # Эта строка не будет достигнута, так как Pydantic вызовет ошибку выше
            uow.words.create_cached_word(word_to_create)

    # После ошибки и автоматического отката слово не должно существовать в БД
    found_word = repo.find_words_by_normalized_form("להכשל")
    assert not found_word, "Слово не должно было быть создано из-за отката транзакции."

    connection.close()
