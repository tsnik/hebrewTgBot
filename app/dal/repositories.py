# -*- coding: utf-8 -*-

from typing import Optional, Dict, Any, List
from datetime import datetime
import sqlite3

from dal.models import (
    CachedWord,
    Translation,
    VerbConjugation,
    UserSettings,
    UserTenseSetting,
    Tense,
)


class BaseRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def _row_to_model(self, row: sqlite3.Row, model_class):
        # Explicitly convert sqlite3.Row to dict for robust Pydantic model creation
        return model_class(**dict(row)) if row else None

    def _rows_to_models(self, rows: List[sqlite3.Row], model_class):
        return [self._row_to_model(row, model_class) for row in rows] if rows else []


class WordRepository(BaseRepository):
    def get_word_by_id(self, word_id: int) -> Optional[CachedWord]:
        query = "SELECT * FROM cached_words WHERE word_id = ?"
        cursor = self.connection.cursor()
        cursor.execute(query, (word_id,))
        word_data = cursor.fetchone()
        if not word_data:
            return None

        word = self._row_to_model(word_data, CachedWord)
        if not word:
            return None
        word.translations = self.get_translations_for_word(word_id)
        word.conjugations = self.get_conjugations_for_word(word_id)
        return word

    def get_translations_for_word(self, word_id: int) -> List[Translation]:
        query = "SELECT * FROM translations WHERE word_id = ? ORDER BY is_primary DESC"
        cursor = self.connection.cursor()
        cursor.execute(query, (word_id,))
        translations_data = cursor.fetchall()
        return self._rows_to_models(translations_data, Translation)

    def get_conjugations_for_word(self, word_id: int) -> List[VerbConjugation]:
        query = "SELECT * FROM verb_conjugations WHERE word_id = ? ORDER BY id"
        cursor = self.connection.cursor()
        cursor.execute(query, (word_id,))
        conjugations_data = cursor.fetchall()
        return self._rows_to_models(conjugations_data, VerbConjugation)

    def get_random_verb_for_training(self, user_id: int) -> Optional[CachedWord]:
        # *** ADAPTED FOR NEW MODEL ***
        query = """
            SELECT cw.*
            FROM cached_words cw
            JOIN user_dictionary ud ON cw.word_id = ud.word_id
            WHERE ud.user_id = ? AND cw.part_of_speech = 'verb'
            ORDER BY RANDOM()
            LIMIT 1
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id,))
        word_data = cursor.fetchone()
        return self._row_to_model(word_data, CachedWord)

    def get_random_conjugation_for_word(
        self, word_id: int, active_tenses: List[str]
    ) -> Optional[VerbConjugation]:
        """Возвращает случайное спряжение для слова, но только из списка активных времен."""
        if not active_tenses:
            return None

        placeholders = ", ".join(["?"] * len(active_tenses))
        query = f"SELECT * FROM verb_conjugations WHERE word_id = ? AND tense IN ({placeholders}) ORDER BY RANDOM() LIMIT 1"

        cursor = self.connection.cursor()
        cursor.execute(query, (word_id, *active_tenses))
        conjugation_data = cursor.fetchone()
        return self._row_to_model(conjugation_data, VerbConjugation)

    def find_word_by_normalized_form(
        self, normalized_word: str, only_normalized_form: Optional[bool] = False
    ) -> Optional[CachedWord]:
        cursor = self.connection.cursor()
        word_id = None

        word_query = "SELECT word_id FROM cached_words WHERE normalized_hebrew = ?"
        cursor.execute(word_query, (normalized_word,))
        word_data_row = cursor.fetchone()
        if word_data_row:
            word_id = word_data_row["word_id"]

        if word_id is None and not only_normalized_form:
            conjugation_query = (
                "SELECT word_id FROM verb_conjugations WHERE normalized_hebrew_form = ?"
            )
            cursor.execute(conjugation_query, (normalized_word,))
            conjugation = cursor.fetchone()
            if conjugation:
                word_id = conjugation["word_id"]

        if not word_id:
            return None

        return self.get_word_by_id(word_id)

    def find_words_by_normalized_form(self, normalized_word: str) -> List[CachedWord]:
        """Ищет все канонические слова, совпадающие с нормализованной формой."""
        cursor = self.connection.cursor()
        query = "SELECT word_id FROM cached_words WHERE normalized_hebrew = ?"
        cursor.execute(query, (normalized_word,))
        word_ids = [row["word_id"] for row in cursor.fetchall()]

        # Также ищем по формам спряжений, чтобы найти инфинитив
        conj_query = "SELECT DISTINCT word_id FROM verb_conjugations WHERE normalized_hebrew_form = ?"
        cursor.execute(conj_query, (normalized_word,))
        conj_word_ids = [row["word_id"] for row in cursor.fetchall()]

        all_ids = list(set(word_ids + conj_word_ids))

        if not all_ids:
            return []

        return [self.get_word_by_id(word_id) for word_id in all_ids if word_id]

    def get_word_hebrew_by_id(self, word_id: int) -> Optional[str]:
        query = "SELECT hebrew FROM cached_words WHERE word_id = ?"
        cursor = self.connection.cursor()
        cursor.execute(query, (word_id,))
        result = cursor.fetchone()
        return result["hebrew"] if result else None

    def create_cached_word(
        self,
        hebrew: str,
        normalized_hebrew: str,
        transcription: Optional[str],
        is_verb: bool,
        root: Optional[str],
        binyan: Optional[str],
        translations: List[Dict[str, Any]],
        conjugations: List[Dict[str, Any]],
        **kwargs,
    ) -> int:
        cursor = self.connection.cursor()

        part_of_speech = "verb" if is_verb else kwargs.get("part_of_speech")

        word_data = {
            "hebrew": hebrew,
            "normalized_hebrew": normalized_hebrew,
            "transcription": transcription,
            "part_of_speech": part_of_speech,
            "root": root,
            "binyan": binyan,
            "fetched_at": datetime.now(),
            **kwargs,
        }

        # validation
        CachedWord(word_id=-1, **word_data)

        # Remove is_verb if it exists in kwargs to avoid column error
        word_data.pop("is_verb", None)

        columns = ", ".join(word_data.keys())
        placeholders = ", ".join(["?"] * len(word_data))
        word_query = f"INSERT INTO cached_words ({columns}) VALUES ({placeholders})"

        cursor.execute(word_query, list(word_data.values()))
        word_id = cursor.lastrowid
        if not word_id:
            raise Exception("Failed to get last row id for new word.")

        if translations:
            translations_to_insert = [
                (
                    word_id,
                    t["translation_text"],
                    t.get("context_comment"),
                    t["is_primary"],
                )
                for t in translations
            ]
            [Translation(**t, word_id=word_id, translation_id=-1) for t in translations]
            translations_query = "INSERT INTO translations (word_id, translation_text, context_comment, is_primary) VALUES (?, ?, ?, ?)"
            cursor.executemany(translations_query, translations_to_insert)

        if conjugations:
            conjugations_to_insert = [
                (
                    word_id,
                    c["tense"],
                    c["person"],
                    c["hebrew_form"],
                    c["normalized_hebrew_form"],
                    c["transcription"],
                )
                for c in conjugations
            ]
            [VerbConjugation(**c, word_id=word_id, id=-1) for c in conjugations]
            conjugations_query = "INSERT INTO verb_conjugations (word_id, tense, person, hebrew_form, normalized_hebrew_form, transcription) VALUES (?, ?, ?, ?, ?, ?)"
            cursor.executemany(conjugations_query, conjugations_to_insert)

        return word_id


class UserDictionaryRepository(BaseRepository):
    def add_user(self, user_id: int, first_name: str, username: Optional[str]):
        query = "INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, first_name, username))

    def add_word_to_dictionary(self, user_id: int, word_id: int):
        query = "INSERT OR IGNORE INTO user_dictionary (user_id, word_id, next_review_at) VALUES (?, ?, ?)"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, word_id, datetime.now()))

    def remove_word_from_dictionary(self, user_id: int, word_id: int):
        query = "DELETE FROM user_dictionary WHERE user_id = ? AND word_id = ?"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, word_id))

    def get_dictionary_page(
        self, user_id: int, page: int, page_size: int
    ) -> List[CachedWord]:
        limit = page_size + 1
        offset = page * page_size
        query = """
            SELECT cw.*
            FROM cached_words cw
            JOIN user_dictionary ud ON cw.word_id = ud.word_id
            WHERE ud.user_id = ?
            ORDER BY ud.added_at DESC
            LIMIT ? OFFSET ?
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, limit, offset))
        word_data_rows = cursor.fetchall()
        words = self._rows_to_models(word_data_rows, CachedWord)
        word_repo = WordRepository(self.connection)
        for word in words:
            word.translations = word_repo.get_translations_for_word(word.word_id)
        return words

    def is_word_in_dictionary(self, user_id: int, word_id: int) -> bool:
        query = "SELECT 1 FROM user_dictionary WHERE user_id = ? AND word_id = ?"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, word_id))
        result = cursor.fetchone()
        return result is not None

    def get_user_words_for_training(self, user_id: int, limit: int) -> List[CachedWord]:
        # *** ADAPTED FOR NEW MODEL ***
        query = """
            SELECT cw.*
            FROM cached_words cw
            JOIN user_dictionary ud ON cw.word_id = ud.word_id
            WHERE ud.user_id = ? AND (cw.part_of_speech != 'verb' OR cw.part_of_speech IS NULL)
            ORDER BY ud.next_review_at ASC
            LIMIT ?
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, limit))
        word_data_rows = cursor.fetchall()
        words = self._rows_to_models(word_data_rows, CachedWord)
        word_repo = WordRepository(self.connection)
        for word in words:
            word.translations = word_repo.get_translations_for_word(word.word_id)
        return words

    def get_srs_level(self, user_id: int, word_id: int) -> Optional[int]:
        query = (
            "SELECT srs_level FROM user_dictionary WHERE user_id = ? AND word_id = ?"
        )
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, word_id))
        result = cursor.fetchone()
        return result["srs_level"] if result else None

    def update_srs_level(
        self, srs_level: int, next_review_at: datetime, user_id: int, word_id: int
    ):
        query = "UPDATE user_dictionary SET srs_level = ?, next_review_at = ? WHERE user_id = ? AND word_id = ?"
        cursor = self.connection.cursor()
        cursor.execute(query, (srs_level, next_review_at, user_id, word_id))


class UserSettingsRepository(BaseRepository):
    def get_user_settings(self, user_id: int) -> UserSettings:
        # 1. Получаем все настройки времен из БД
        query = "SELECT tense, is_active FROM user_tense_settings WHERE user_id = ?"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id,))
        rows = cursor.fetchall()

        tense_settings_list = [
            UserTenseSetting(
                user_id=user_id, tense=row["tense"], is_active=bool(row["is_active"])
            )
            for row in rows
        ]

        if len(tense_settings_list) == 0:
            tense_settings_list = None

        # 2. Создаем и возвращаем единый объект UserSettings
        return UserSettings(user_id=user_id, tense_settings=tense_settings_list)

    def initialize_tense_settings(self, user_id: int):
        """Создает набор настроек по умолчанию для пользователя."""
        default_settings = [
            (user_id, "perf", True),
            (user_id, "ap", True),
            (user_id, "impf", True),
            (user_id, "imp", True),
        ]
        query = "INSERT OR IGNORE INTO user_tense_settings (user_id, tense, is_active) VALUES (?, ?, ?)"
        cursor = self.connection.cursor()
        cursor.executemany(query, default_settings)

    def toggle_tense_setting(self, user_id: int, tense: Tense):  # Принимаем Enum
        """Переключает статус (активно/неактивно) для указанного времени."""
        query = "UPDATE user_tense_settings SET is_active = NOT is_active WHERE user_id = ? AND tense = ?"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, tense.value))  # Используем .value для SQL
