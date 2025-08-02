# -*- coding: utf-8 -*-

from typing import Optional, List, Any, Dict
from datetime import datetime

from psycopg2.extras import DictRow

from dal.models import (
    CachedWord,
    CreateCachedWord,
    Translation,
    VerbConjugation,
    UserSettings,
    UserTenseSetting,
    Tense,
)
from services.connection import Connection


class BaseRepository:
    def __init__(self, connection: Connection, is_postgres: bool = True):
        self.connection = connection
        self.is_postgres = is_postgres
        self.param_style = "%s" if is_postgres else "?"

    def _row_to_model(self, row: Dict[str, Any], model_class):
        # Преобразование DictRow от psycopg2 в стандартный dict
        if isinstance(row, DictRow):
            row = dict(row)
        return model_class(**row) if row else None

    def _rows_to_models(self, rows: List[Dict[str, Any]], model_class):
        return [self._row_to_model(row, model_class) for row in rows] if rows else []


class WordRepository(BaseRepository):
    def get_word_by_id(self, word_id: int) -> Optional[CachedWord]:
        query = f"SELECT * FROM cached_words WHERE word_id = {self.param_style}"
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
        query = f"SELECT * FROM translations WHERE word_id = {self.param_style} ORDER BY is_primary DESC"
        cursor = self.connection.cursor()
        cursor.execute(query, (word_id,))
        translations_data = cursor.fetchall()
        return self._rows_to_models(translations_data, Translation)

    def get_conjugations_for_word(self, word_id: int) -> List[VerbConjugation]:
        query = f"SELECT * FROM verb_conjugations WHERE word_id = {self.param_style} ORDER BY id"
        cursor = self.connection.cursor()
        cursor.execute(query, (word_id,))
        conjugations_data = cursor.fetchall()
        return self._rows_to_models(conjugations_data, VerbConjugation)

    def get_random_verb_for_training(self, user_id: int) -> Optional[CachedWord]:
        order_by_clause = "RANDOM()" if not self.is_postgres else "RANDOM()"
        query = f"""
            SELECT cw.*
            FROM cached_words cw
            JOIN user_dictionary ud ON cw.word_id = ud.word_id
            WHERE ud.user_id = {self.param_style} AND cw.part_of_speech = 'verb'
            ORDER BY {order_by_clause}
            LIMIT 1
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id,))
        word_data = cursor.fetchone()
        return self._row_to_model(word_data, CachedWord)

    def get_random_conjugation_for_word(
        self, word_id: int, active_tenses: List[str]
    ) -> Optional[VerbConjugation]:
        if not active_tenses:
            return None

        placeholders = ", ".join([self.param_style] * len(active_tenses))
        order_by_clause = "RANDOM()" if not self.is_postgres else "RANDOM()"
        query = f"""
            SELECT * FROM verb_conjugations
            WHERE word_id = {self.param_style} AND tense IN ({placeholders})
            ORDER BY {order_by_clause} LIMIT 1
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (word_id, *active_tenses))
        conjugation_data = cursor.fetchone()
        return self._row_to_model(conjugation_data, VerbConjugation)

    def find_word_by_normalized_form(
        self, normalized_word: str, only_normalized_form: Optional[bool] = False
    ) -> Optional[CachedWord]:
        cursor = self.connection.cursor()
        word_id = None

        word_query = f"SELECT word_id FROM cached_words WHERE normalized_hebrew = {self.param_style}"
        cursor.execute(word_query, (normalized_word,))
        word_data_row = cursor.fetchone()
        if word_data_row:
            word_id = word_data_row["word_id"]

        if word_id is None and not only_normalized_form:
            conjugation_query = f"SELECT word_id FROM verb_conjugations WHERE normalized_hebrew_form = {self.param_style}"
            cursor.execute(conjugation_query, (normalized_word,))
            conjugation = cursor.fetchone()
            if conjugation:
                word_id = conjugation["word_id"]

        if not word_id:
            return None

        return self.get_word_by_id(word_id)

    def find_words_by_normalized_form(self, normalized_word: str) -> List[CachedWord]:
        cursor = self.connection.cursor()
        query = f"SELECT word_id FROM cached_words WHERE normalized_hebrew = {self.param_style}"
        cursor.execute(query, (normalized_word,))
        word_ids = [row["word_id"] for row in cursor.fetchall()]

        conj_query = f"SELECT DISTINCT word_id FROM verb_conjugations WHERE normalized_hebrew_form = {self.param_style}"
        cursor.execute(conj_query, (normalized_word,))
        conj_word_ids = [row["word_id"] for row in cursor.fetchall()]

        all_ids = list(set(word_ids + conj_word_ids))

        if not all_ids:
            return []

        return [self.get_word_by_id(word_id) for word_id in all_ids if word_id]

    def get_word_hebrew_by_id(self, word_id: int) -> Optional[str]:
        query = f"SELECT hebrew FROM cached_words WHERE word_id = {self.param_style}"
        cursor = self.connection.cursor()
        cursor.execute(query, (word_id,))
        result = cursor.fetchone()
        return result["hebrew"] if result else None

    def create_cached_word(self, word_data: CreateCachedWord) -> int:
        cursor = self.connection.cursor()

        word_db_data = word_data.model_dump(exclude={"translations", "conjugations"})
        word_db_data["fetched_at"] = datetime.now()

        columns = ", ".join(word_db_data.keys())
        placeholders = ", ".join([self.param_style] * len(word_db_data))
        word_query = f"INSERT INTO cached_words ({columns}) VALUES ({placeholders})"

        if self.is_postgres:
            word_query += " RETURNING word_id"

        cursor.execute(word_query, list(word_db_data.values()))

        if self.is_postgres:
            word_id = cursor.fetchone()["word_id"]
        else:
            word_id = cursor.lastrowid

        if not word_id:
            raise Exception("Failed to get last row id for new word.")

        if word_data.translations:
            translations_to_insert = [
                (word_id, t.translation_text, t.context_comment, t.is_primary)
                for t in word_data.translations
            ]
            trans_cols = "word_id, translation_text, context_comment, is_primary"
            trans_placeholders = f"{self.param_style}, {self.param_style}, {self.param_style}, {self.param_style}"
            translations_query = (
                f"INSERT INTO translations ({trans_cols}) VALUES ({trans_placeholders})"
            )
            cursor.executemany(translations_query, translations_to_insert)

        if hasattr(word_data, "conjugations") and word_data.conjugations:
            conjugations_to_insert = [
                (
                    word_id,
                    c.tense.value,
                    c.person.value,
                    c.hebrew_form,
                    c.normalized_hebrew_form,
                    c.transcription,
                )
                for c in word_data.conjugations
            ]
            conj_cols = "word_id, tense, person, hebrew_form, normalized_hebrew_form, transcription"
            conj_placeholders = f"{self.param_style}, {self.param_style}, {self.param_style}, {self.param_style}, {self.param_style}, {self.param_style}"
            conjugations_query = f"INSERT INTO verb_conjugations ({conj_cols}) VALUES ({conj_placeholders})"
            cursor.executemany(conjugations_query, conjugations_to_insert)

        return word_id


class UserDictionaryRepository(BaseRepository):
    def add_user(self, user_id: int, first_name: str, username: Optional[str]):
        if self.is_postgres:
            query = f"INSERT INTO users (user_id, first_name, username) VALUES ({self.param_style}, {self.param_style}, {self.param_style}) ON CONFLICT (user_id) DO NOTHING"
        else:
            query = f"INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES ({self.param_style}, {self.param_style}, {self.param_style})"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, first_name, username))

    def add_word_to_dictionary(self, user_id: int, word_id: int):
        if self.is_postgres:
            query = f"INSERT INTO user_dictionary (user_id, word_id, next_review_at) VALUES ({self.param_style}, {self.param_style}, {self.param_style}) ON CONFLICT (user_id, word_id) DO NOTHING"
        else:
            query = f"INSERT OR IGNORE INTO user_dictionary (user_id, word_id, next_review_at) VALUES ({self.param_style}, {self.param_style}, {self.param_style})"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, word_id, datetime.now()))

    def remove_word_from_dictionary(self, user_id: int, word_id: int):
        query = f"DELETE FROM user_dictionary WHERE user_id = {self.param_style} AND word_id = {self.param_style}"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, word_id))

    def get_dictionary_page(
        self, user_id: int, page: int, page_size: int
    ) -> List[CachedWord]:
        limit = page_size + 1
        offset = page * page_size
        query = f"""
            SELECT cw.*
            FROM cached_words cw
            JOIN user_dictionary ud ON cw.word_id = ud.word_id
            WHERE ud.user_id = {self.param_style}
            ORDER BY ud.added_at DESC
            LIMIT {self.param_style} OFFSET {self.param_style}
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, limit, offset))
        word_data_rows = cursor.fetchall()
        words = self._rows_to_models(word_data_rows, CachedWord)
        word_repo = WordRepository(self.connection, self.is_postgres)
        for word in words:
            word.translations = word_repo.get_translations_for_word(word.word_id)
        return words

    def is_word_in_dictionary(self, user_id: int, word_id: int) -> bool:
        query = f"SELECT 1 FROM user_dictionary WHERE user_id = {self.param_style} AND word_id = {self.param_style}"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, word_id))
        result = cursor.fetchone()
        return result is not None

    def get_user_words_for_training(self, user_id: int, limit: int) -> List[CachedWord]:
        order_by_clause = "ud.next_review_at ASC"
        query = f"""
            SELECT cw.*
            FROM cached_words cw
            JOIN user_dictionary ud ON cw.word_id = ud.word_id
            WHERE ud.user_id = {self.param_style} AND (cw.part_of_speech != 'verb' OR cw.part_of_speech IS NULL)
            ORDER BY {order_by_clause}
            LIMIT {self.param_style}
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, limit))
        word_data_rows = cursor.fetchall()
        words = self._rows_to_models(word_data_rows, CachedWord)
        word_repo = WordRepository(self.connection, self.is_postgres)
        for word in words:
            word.translations = word_repo.get_translations_for_word(word.word_id)
        return words

    def get_srs_level(self, user_id: int, word_id: int) -> Optional[int]:
        query = f"SELECT srs_level FROM user_dictionary WHERE user_id = {self.param_style} AND word_id = {self.param_style}"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, word_id))
        result = cursor.fetchone()
        return result["srs_level"] if result else None

    def update_srs_level(
        self, srs_level: int, next_review_at: datetime, user_id: int, word_id: int
    ):
        query = f"""
            UPDATE user_dictionary
            SET srs_level = {self.param_style}, next_review_at = {self.param_style}
            WHERE user_id = {self.param_style} AND word_id = {self.param_style}
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (srs_level, next_review_at, user_id, word_id))


class UserSettingsRepository(BaseRepository):
    def get_user_settings(self, user_id: int) -> UserSettings:
        # 1. Получаем настройки времен
        tense_query = f"SELECT tense, is_active FROM user_tense_settings WHERE user_id = {self.param_style}"
        cursor = self.connection.cursor()
        cursor.execute(tense_query, (user_id,))
        tense_rows = cursor.fetchall()

        tense_settings_list = (
            [
                UserTenseSetting(
                    user_id=user_id,
                    tense=row["tense"],
                    is_active=bool(row["is_active"]),
                )
                for row in tense_rows
            ]
            if tense_rows
            else None
        )

        # 2. Получаем настройки режима тренировки
        training_mode_query = f"SELECT use_grammatical_forms FROM user_settings WHERE user_id = {self.param_style}"
        cursor.execute(training_mode_query, (user_id,))
        training_mode_row = cursor.fetchone()
        use_grammatical_forms = (
            bool(training_mode_row["use_grammatical_forms"])
            if training_mode_row
            else False
        )

        # 3. Собираем всё в одну модель
        return UserSettings(
            user_id=user_id,
            tense_settings=tense_settings_list,
            use_grammatical_forms=use_grammatical_forms,
        )

    def initialize_tense_settings(self, user_id: int):
        default_settings = [
            (user_id, "perf", True),
            (user_id, "ap", True),
            (user_id, "impf", True),
            (user_id, "imp", True),
        ]
        if self.is_postgres:
            query = f"INSERT INTO user_tense_settings (user_id, tense, is_active) VALUES ({self.param_style}, {self.param_style}, {self.param_style}) ON CONFLICT (user_id, tense) DO NOTHING"
        else:
            query = f"INSERT OR IGNORE INTO user_tense_settings (user_id, tense, is_active) VALUES ({self.param_style}, {self.param_style}, {self.param_style})"
        cursor = self.connection.cursor()
        cursor.executemany(query, default_settings)

    def initialize_user_settings(self, user_id: int):
        # Новый метод для инициализации записи в user_settings [cite: 161-162]
        if self.is_postgres:
            query = f"INSERT INTO user_settings (user_id, use_grammatical_forms) VALUES ({self.param_style}, FALSE) ON CONFLICT (user_id) DO NOTHING"
        else:
            query = f"INSERT OR IGNORE INTO user_settings (user_id, use_grammatical_forms) VALUES ({self.param_style}, 0)"
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id,))

    def toggle_tense_setting(self, user_id: int, tense: Tense):
        query = f"""
            UPDATE user_tense_settings
            SET is_active = NOT is_active
            WHERE user_id = {self.param_style} AND tense = {self.param_style}
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id, tense.value))

    def toggle_training_mode(self, user_id: int):
        # Новый метод для переключения режима тренировки [cite: 165-166]
        query = f"""
            UPDATE user_settings
            SET use_grammatical_forms = NOT use_grammatical_forms
            WHERE user_id = {self.param_style}
        """
        cursor = self.connection.cursor()
        cursor.execute(query, (user_id,))
