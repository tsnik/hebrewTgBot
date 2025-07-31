# -*- coding: utf-8 -*-

from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class PartOfSpeech(str, Enum):
    VERB = "verb"
    NOUN = "noun"
    ADJECTIVE = "adjective"


class Gender(str, Enum):
    MASCULINE = "masculine"
    FEMININE = "feminine"


class Tense(str, Enum):
    PAST = "perf"
    PRESENT = "ap"
    FUTURE = "impf"
    IMPERATIVE = "imp"
    INFINITIVE = "inf"


class Person(str, Enum):
    MS = "ms"
    FS = "fs"
    MP = "mp"
    FP = "fp"
    S1 = "1s"
    P1 = "1p"
    S2_M = "2ms"
    S2_F = "2fs"
    P2_M = "2mp"
    P2_F = "2fp"
    S3_M = "3ms"
    S3_F = "3fs"
    P3 = "3p"
    P3_M = "3mp"
    P3_F = "3fp"
    L = "L"


class Binyan(str, Enum):
    PAAL = "paal"
    PIEL = "piel"
    NIFAL = "nifal"
    HIFIL = "hifil"
    HITPAEL = "hitpael"
    PUAL = "pual"
    HUFAL = "hufal"


class Translation(BaseModel):
    translation_id: int
    word_id: int
    translation_text: str
    context_comment: Optional[str] = None
    is_primary: bool


class VerbConjugation(BaseModel):
    id: int
    word_id: int
    tense: Tense
    person: Person
    hebrew_form: str
    normalized_hebrew_form: str
    transcription: str


class CachedWord(BaseModel):
    word_id: int
    hebrew: str
    normalized_hebrew: str
    transcription: Optional[str] = None
    part_of_speech: Optional[PartOfSpeech] = None
    root: Optional[str] = None
    binyan: Optional[Binyan] = None
    fetched_at: datetime
    translations: List[Translation] = []
    conjugations: List[VerbConjugation] = []
    gender: Optional[Gender] = None
    singular_form: Optional[str] = None
    plural_form: Optional[str] = None
    masculine_singular: Optional[str] = None
    feminine_singular: Optional[str] = None
    masculine_plural: Optional[str] = None
    feminine_plural: Optional[str] = None


class CreateTranslation(BaseModel):
    """Модель для данных о новом переводе."""

    translation_text: str
    context_comment: Optional[str] = None
    is_primary: bool


class CreateVerbConjugation(BaseModel):
    """Модель для данных о новом спряжении."""

    tense: Tense
    person: Person
    hebrew_form: str
    normalized_hebrew_form: str
    transcription: str


class CreateCachedWord(BaseModel):
    hebrew: str
    normalized_hebrew: str
    transcription: Optional[str]
    part_of_speech: PartOfSpeech
    root: Optional[str] = None
    binyan: Optional[Binyan] = None
    translations: List[CreateTranslation]
    conjugations: List[CreateVerbConjugation] = []
    gender: Optional[Gender] = None
    singular_form: Optional[str] = None
    plural_form: Optional[str] = None
    masculine_singular: Optional[str] = None
    feminine_singular: Optional[str] = None
    masculine_plural: Optional[str] = None
    feminine_plural: Optional[str] = None


class UserDictionaryEntry(BaseModel):
    id: int
    user_id: int
    word_id: int
    added_at: datetime
    srs_level: int
    next_review_at: datetime
    word: CachedWord


class UserTenseSetting(BaseModel):
    user_id: int
    tense: Tense
    is_active: bool


class UserSettings(BaseModel):
    user_id: int
    tense_settings: Optional[List[UserTenseSetting]] = None

    def get_active_tenses(self) -> List[str]:
        """Возвращает список активных времен в виде строк."""
        return [
            setting.tense.value for setting in self.tense_settings if setting.is_active
        ]

    def get_settings_as_dict(self) -> Dict[str, bool]:
        """Возвращает настройки в виде словаря. Удобно для быстрой проверки."""
        return {
            setting.tense.value: setting.is_active for setting in self.tense_settings
        }
