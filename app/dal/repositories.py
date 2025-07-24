# -*- coding: utf-8 -*-

from typing import Optional, Dict, Any, List
from datetime import datetime

from services.database import db_read_query, db_write_query, db_transaction
from .models import CachedWord, Translation, VerbConjugation


class BaseRepository:
    def __init__(self):
        self._db_read = db_read_query
        self._db_write = db_write_query
        self._db_transaction = db_transaction

    def _row_to_model(self, row: Dict[str, Any], model_class):
        return model_class(**row) if row else None

    def _rows_to_models(self, rows: List[Dict[str, Any]], model_class):
        return [self._row_to_model(row, model_class) for row in rows] if rows else []


class WordRepository(BaseRepository):
    def get_word_by_id(self, word_id: int) -> Optional[CachedWord]:
        query = "SELECT * FROM cached_words WHERE word_id = ?"
        word_data = self._db_read(query, (word_id,), fetchone=True)
        if not word_data:
            return None

        word = self._row_to_model(word_data, CachedWord)
        word.translations = self.get_translations_for_word(word_id)
        word.conjugations = self.get_conjugations_for_word(word_id)
        return word

    def get_translations_for_word(self, word_id: int) -> List[Translation]:
        query = "SELECT * FROM translations WHERE word_id = ? ORDER BY is_primary DESC"
        translations_data = self._db_read(query, (word_id,), fetchall=True)
        return self._rows_to_models(translations_data, Translation)

    def get_conjugations_for_word(self, word_id: int) -> List[VerbConjugation]:
        query = "SELECT * FROM verb_conjugations WHERE word_id = ? ORDER BY id"
        conjugations_data = self._db_read(query, (word_id,), fetchall=True)
        return self._rows_to_models(conjugations_data, VerbConjugation)

    def find_word_by_normalized_form(self, normalized_word: str) -> Optional[CachedWord]:
        word_id = None

        # 1. Поиск по формам глаголов
        conjugation_query = "SELECT word_id FROM verb_conjugations WHERE normalized_hebrew_form = ?"
        conjugation = self._db_read(conjugation_query, (normalized_word,), fetchone=True)
        if conjugation:
            word_id = conjugation['word_id']
        else:
            # 2. Поиск по каноническим формам
            word_query = "SELECT word_id FROM cached_words WHERE normalized_hebrew = ?"
            word_data_row = self._db_read(word_query, (normalized_word,), fetchone=True)
            if word_data_row:
                word_id = word_data_row['word_id']

        if not word_id:
            return None

        return self.get_word_by_id(word_id)

    def get_word_hebrew_by_id(self, word_id: int) -> Optional[str]:
        query = "SELECT hebrew FROM cached_words WHERE word_id = ?"
        result = self._db_read(query, (word_id,), fetchone=True)
        return result['hebrew'] if result else None

    def create_cached_word(
        self,
        hebrew: str,
        normalized_hebrew: str,
        transcription: Optional[str],
        is_verb: bool,
        root: Optional[str],
        binyan: Optional[str],
        translations: List[Dict[str, Any]],
        conjugations: List[Dict[str, Any]]
    ) -> Optional[int]:

        def transaction_logic(cursor):
            # 1. Вставляем основное слово
            word_query = """
                INSERT INTO cached_words
                (hebrew, normalized_hebrew, transcription, is_verb, root, binyan, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            cursor.execute(word_query, (
                hebrew, normalized_hebrew, transcription, is_verb, root, binyan, datetime.now()
            ))
            word_id = cursor.lastrowid
            if not word_id:
                raise Exception("Failed to get last row id for new word.")

            # 2. Вставляем переводы
            if translations:
                translations_to_insert = [
                    (word_id, t['translation_text'], t.get('context_comment'), t['is_primary'])
                    for t in translations
                ]
                translations_query = """
                    INSERT INTO translations (word_id, translation_text, context_comment, is_primary)
                    VALUES (?, ?, ?, ?)
                """
                cursor.executemany(translations_query, translations_to_insert)

            # 3. Вставляем спряжения
            if conjugations:
                conjugations_to_insert = [
                    (word_id, c['tense'], c['person'], c['hebrew_form'], c['normalized_hebrew_form'], c['transcription'])
                    for c in conjugations
                ]
                conjugations_query = """
                    INSERT INTO verb_conjugations
                    (word_id, tense, person, hebrew_form, normalized_hebrew_form, transcription)
                    VALUES (?, ?, ?, ?, ?, ?)
                """
                cursor.executemany(conjugations_query, conjugations_to_insert)

            # Возвращаем word_id из транзакции
            # Прямой возврат значения из функции транзакции невозможен,
            # поэтому используем трюк с mutable объектом (list) для его передачи.
            result_container[0] = word_id

        result_container = [None]
        try:
            self._db_transaction(transaction_logic)
            return result_container[0]
        except Exception as e:
            # Логируем ошибку, если нужно
            return None


class UserDictionaryRepository(BaseRepository):
    def add_word_to_dictionary(self, user_id: int, word_id: int):
        query = "INSERT OR IGNORE INTO user_dictionary (user_id, word_id, next_review_at) VALUES (?, ?, ?)"
        self._db_write(query, (user_id, word_id, datetime.now()))

    def remove_word_from_dictionary(self, user_id: int, word_id: int):
        query = "DELETE FROM user_dictionary WHERE user_id = ? AND word_id = ?"
        self._db_write(query, (user_id, word_id))

    def get_dictionary_page(self, user_id: int, page: int, page_size: int) -> List[Dict[str, Any]]:
        limit = page_size + 1
        offset = page * page_size
        query = """
            SELECT cw.word_id, cw.hebrew, t.translation_text
            FROM cached_words cw
            JOIN user_dictionary ud ON cw.word_id = ud.word_id
            JOIN translations t ON cw.word_id = t.word_id
            WHERE ud.user_id = ? AND t.is_primary = 1
            ORDER BY ud.added_at DESC
            LIMIT ? OFFSET ?
        """
        return self._db_read(query, (user_id, limit, offset), fetchall=True)

    def is_word_in_dictionary(self, user_id: int, word_id: int) -> bool:
        query = "SELECT 1 FROM user_dictionary WHERE user_id = ? AND word_id = ?"
        result = self._db_read(query, (user_id, word_id), fetchone=True)
        return result is not None
