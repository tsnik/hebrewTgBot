import pytest
from datetime import datetime, timedelta

# Импортируем Pydantic-модели для создания данных
from dal.models import (
    CreateVerb,
    CreateNoun,
    CreateAdjective,
    CreateTranslation,
    CreateVerbConjugation,
    PartOfSpeech,
    Tense,
    Person,
    Binyan,
)
from dal.repositories import WordRepository, UserDictionaryRepository
from dal.unit_of_work import UnitOfWork


def test_word_repository(db_session):
    """Тестирует базовые операции WordRepository с новыми моделями."""
    connection = db_session
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

    word_to_create = CreateVerb(
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


def test_srs_level_management(db_session):
    """Тестирует управление SRS-уровнем слова."""
    connection = db_session
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 101
    srs_level = 5
    next_review_at = datetime(2025, 1, 1, 10, 0, 0)

    with connection:
        user_repo.add_user(user_id, "SRS", "User")
        word_to_create = CreateVerb(
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


def test_get_random_verb_for_training(db_session):
    """Тестирует получение случайного глагола для тренировки."""
    connection = db_session
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 456

    with connection:
        user_repo.add_user(user_id, "Train", "User")
        verb_to_create = CreateVerb(
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


def test_find_words_by_normalized_form(db_session):
    """Тестирует поиск слов по нормализованной форме."""
    connection = db_session
    repo = WordRepository(connection)

    with connection:
        word_to_create = CreateNoun(
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


def test_get_word_by_id(db_session):
    """Тестирует получение слова по его ID."""
    connection = db_session
    repo = WordRepository(connection)

    with connection:
        word_to_create = CreateVerb(
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


def test_user_dictionary_repository(db_session):
    """Тестирует полный цикл операций со словарём пользователя."""
    connection = db_session
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 123

    with connection:
        user_repo.add_user(user_id, "Test", "User")
        word_to_create = CreateNoun(
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


def test_word_repository_transaction_rollback(db_session):
    """Тестирует, что транзакция откатывается при ошибке."""
    connection = db_session
    repo = WordRepository(connection)

    # Создаем заведомо невалидные данные (неправильный тип в списке)
    invalid_translations = [1, 2, 3]

    with pytest.raises(Exception):  # Ловим любую ошибку (Pydantic или TypeError)
        with UnitOfWork() as uow:
            # Пытаемся создать модель с невалидными данными
            word_to_create = CreateVerb(
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


def test_optimized_word_selection_for_training(db_session):
    """
    Тестирует оптимизированную выборку слов (включая глаголы).
    """
    connection = db_session
    word_repo = WordRepository(connection)
    user_repo = UserDictionaryRepository(connection)
    user_id = 111
    now = datetime.now()

    user_repo.add_user(user_id, "Tester", "tester")

    # Слово 1 (Существительное): Готово к повторению
    noun_model = CreateNoun(
        hebrew="מוכן",
        normalized_hebrew="מוכן",
        transcription="mukhan",  # <-- Добавлено
        part_of_speech=PartOfSpeech.NOUN,
        translations=[CreateTranslation(translation_text="ready", is_primary=True)],
    )
    noun_id = word_repo.create_cached_word(noun_model)
    user_repo.add_word_to_dictionary(user_id, noun_id)
    user_repo.update_srs_level(1, now - timedelta(days=1), user_id, noun_id)

    # Слово 2 (Глагол): Готово к повторению <-- ДОБАВЛЕНО
    verb_model = CreateVerb(
        hebrew="לפעול",
        normalized_hebrew="לפעול",
        transcription="lif'ol",  # <-- Добавлено
        part_of_speech=PartOfSpeech.VERB,
        translations=[CreateTranslation(translation_text="to act", is_primary=True)],
    )
    verb_id = word_repo.create_cached_word(verb_model)
    user_repo.add_word_to_dictionary(user_id, verb_id)
    user_repo.update_srs_level(1, now - timedelta(hours=1), user_id, verb_id)

    # Слово 3: Не готово к повторению
    word3_model = CreateNoun(
        hebrew="לא מוכן",
        normalized_hebrew="לא מוכן",
        transcription="lo mukhan",  # <-- Добавлено
        part_of_speech=PartOfSpeech.NOUN,
        translations=[CreateTranslation(translation_text="not ready", is_primary=True)],
    )
    word3_id = word_repo.create_cached_word(word3_model)
    user_repo.add_word_to_dictionary(user_id, word3_id)
    user_repo.update_srs_level(1, now + timedelta(days=1), user_id, word3_id)

    # 1. Проверяем счетчик (теперь должно быть 2 слова: существительное и глагол)
    ready_count = user_repo.get_ready_for_training_words_count(user_id)
    assert ready_count == 2

    # 2. Проверяем получение слов по смещению
    # Первым будет существительное (самая старая дата), вторым - глагол
    first_word = user_repo.get_word_for_training_with_offset(user_id, 0)
    second_word = user_repo.get_word_for_training_with_offset(user_id, 1)

    assert first_word is not None
    assert first_word.word_id == noun_id
    assert second_word is not None
    assert second_word.word_id == verb_id


@pytest.mark.parametrize(
    "part_of_speech, model_data, expected_forms",
    [
        (
            PartOfSpeech.NOUN,
            {"singular_form": "ספר", "plural_form": "ספרים"},
            [("ספר", "ед.ч."), ("ספרים", "мн.ч.")],
        ),
        (
            PartOfSpeech.ADJECTIVE,
            {
                "masculine_singular": "גדול",
                "feminine_singular": "גדולה",
                "masculine_plural": "גדולים",
                "feminine_plural": "גדולות",
            },
            [
                ("גדול", "м.р., ед.ч."),
                ("גדולה", "ж.р., ед.ч."),
                ("גדולים", "м.р., мн.ч."),
                ("גדולות", "ж.р., мн.ч."),
            ],
        ),
        (
            PartOfSpeech.NOUN,
            {
                "singular_form": "מים",
                "plural_form": None,
            },  # Существительное только в ед.ч.
            [("מים", "ед.ч.")],
        ),
    ],
)
def test_get_random_grammatical_form_for_noun_and_adjective(
    db_session, part_of_speech, model_data, expected_forms
):
    """Тестирует получение случайной формы для существительных и прилагательных."""
    connection = db_session
    word_repo = WordRepository(connection)

    common_data = {
        "hebrew": "тест",
        "normalized_hebrew": "тест",
        "transcription": "test",  # <-- Добавлено
        "part_of_speech": part_of_speech,
        "translations": [],
    }

    if part_of_speech == PartOfSpeech.NOUN:
        create_model = CreateNoun(**common_data, **model_data)
    else:  # ADJECTIVE
        create_model = CreateAdjective(**common_data, **model_data)

    word_id = word_repo.create_cached_word(create_model)

    word_obj = word_repo.get_word_by_id(word_id)

    # Вызываем метод несколько раз, чтобы убедиться, что он возвращает одну из ожидаемых форм
    for _ in range(10):
        form, description = word_repo.get_random_grammatical_form(word_obj, [])
        assert (form, description) in expected_forms


def test_get_random_grammatical_form_for_verb(db_session):
    """Тестирует получение случайной формы для глагола с учетом активных времен."""
    connection = db_session
    word_repo = WordRepository(connection)

    # Создаем глагол с тремя спряжениями в разных временах
    conjugations = [
        CreateVerbConjugation(
            tense=Tense.PAST,
            person=Person.S1,
            hebrew_form="כתבתי",
            normalized_hebrew_form="כתבתי",
            transcription="katavti",
        ),
        CreateVerbConjugation(
            tense=Tense.PRESENT,
            person=Person.MS,
            hebrew_form="כותב",
            normalized_hebrew_form="כותב",
            transcription="kotev",
        ),
        CreateVerbConjugation(
            tense=Tense.IMPERATIVE,
            person=Person.S2_M,
            hebrew_form="כתוב",
            normalized_hebrew_form="כתוב",
            transcription="ktov",
        ),
    ]
    verb_model = CreateVerb(
        hebrew="לכתוב",
        normalized_hebrew="לכתוב",
        transcription="likhtov",
        part_of_speech=PartOfSpeech.VERB,
        translations=[],
        binyan=Binyan.PAAL,
        conjugations=conjugations,
    )

    with connection:
        word_id = word_repo.create_cached_word(verb_model)

    word_obj = word_repo.get_word_by_id(word_id)

    # 1. Тестируем, когда активны только прошедшее и настоящее время
    active_tenses_1 = ["perf", "ap"]
    # --- ИЗМЕНЕНИЕ ЗДЕСЬ: Ожидаемый результат - словарь ---
    expected_forms_1 = [
        ("כתבתי", {"tense": "perf", "person": "1s"}),
        ("כותב", {"tense": "ap", "person": "ms"}),
    ]
    for _ in range(10):
        form, description = word_repo.get_random_grammatical_form(
            word_obj, active_tenses_1
        )
        assert (form, description) in expected_forms_1

    # 2. Тестируем, когда активно только повелительное наклонение
    active_tenses_2 = ["imp"]
    form, description = word_repo.get_random_grammatical_form(word_obj, active_tenses_2)
    assert (form, description) == ("כתוב", {"tense": "imp", "person": "2ms"})
