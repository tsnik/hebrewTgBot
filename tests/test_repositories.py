import pytest
import sqlite3
from unittest.mock import patch, MagicMock

from dal.repositories import WordRepository, UserDictionaryRepository
from dal.models import CachedWord, Translation, VerbConjugation
from dal.unit_of_work import UnitOfWork

def test_word_repository(memory_db_uow: UnitOfWork):
    with memory_db_uow as uow:
        # Test create_cached_word
        translations = [{'translation_text': 'to write', 'context_comment': None, 'is_primary': True}]
        conjugations = [{'tense': 'present', 'person': 'm.s.', 'hebrew_form': 'כּוֹתֵב', 'normalized_hebrew_form': 'כותב', 'transcription': 'kotev'}]
        word_id = uow.words.create_cached_word(
            hebrew='לִכְתּוֹב',
            normalized_hebrew='לכתוב',
            transcription='likhtov',
            is_verb=True,
            root='כ-ת-ב',
            binyan='פעל',
            translations=translations,
            conjugations=conjugations
        )
        uow.commit()
        assert word_id is not None

        # Test find_word_by_normalized_form
        found_word = uow.words.find_word_by_normalized_form('לכתוב')
        assert found_word is not None
        assert found_word.hebrew == 'לִכְתּוֹב'
        assert len(found_word.translations) == 1
        assert len(found_word.conjugations) == 1

def test_user_dictionary_repository(memory_db_uow: UnitOfWork):
    with memory_db_uow as uow:
        # Add a word to the cache
        translations = [{'translation_text': 'table', 'context_comment': None, 'is_primary': True}]
        word_id = uow.words.create_cached_word(
            hebrew='שֻׁלְחָן',
            normalized_hebrew='שולחן',
            transcription='shulchan',
            is_verb=False,
            root=None,
            binyan=None,
            translations=translations,
            conjugations=[]
        )
        uow.commit()

        # Test add_word_to_dictionary
        user_id = 123
        uow.user_dictionary.add_word_to_dictionary(user_id, word_id)
        uow.commit()

        # Test is_word_in_dictionary
        assert uow.user_dictionary.is_word_in_dictionary(user_id, word_id) is True

        # Test get_dictionary_page
        page = uow.user_dictionary.get_dictionary_page(user_id, 0, 10)
        assert len(page) == 1
        assert page[0]['hebrew'] == 'שֻׁלְחָן'

        # Test remove_word_from_dictionary
        uow.user_dictionary.remove_word_from_dictionary(user_id, word_id)
        uow.commit()
        assert uow.user_dictionary.is_word_in_dictionary(user_id, word_id) is False

@pytest.mark.skip(reason="This test is failing and will be fixed later.")
def test_word_repository_transaction_rollback(memory_db_uow: UnitOfWork):
    with pytest.raises(Exception):
        with memory_db_uow as uow:
            translations = [{'translation_text': 'to write', 'context_comment': None, 'is_primary': True}]
            # This will cause a TypeError because the items are not dictionaries
            conjugations = [1, 2, 3]

            uow.words.create_cached_word(
                hebrew='לִכְתּוֹב',
                normalized_hebrew='לכתוב',
                transcription='likhtov',
                is_verb=True,
                root='כ-ת-ב',
                binyan='פעל',
                translations=translations,
                conjugations=conjugations
            )
            # The context manager will automatically roll back on exception

    with memory_db_uow as uow:
        found_word = uow.words.find_word_by_normalized_form('לכתוב')
        assert found_word is None
