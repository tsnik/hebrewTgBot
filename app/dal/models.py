# -*- coding: utf-8 -*-

from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime


class Translation(BaseModel):
    translation_id: int
    word_id: int
    translation_text: str
    context_comment: Optional[str] = None
    is_primary: bool


class VerbConjugation(BaseModel):
    id: int
    word_id: int
    tense: str
    person: str
    hebrew_form: str
    normalized_hebrew_form: str
    transcription: str


class CachedWord(BaseModel):
    word_id: int
    hebrew: str
    normalized_hebrew: str
    transcription: Optional[str] = None
    part_of_speech: Optional[str] = None
    root: Optional[str] = None
    binyan: Optional[str] = None
    fetched_at: datetime
    translations: List[Translation] = []
    conjugations: List[VerbConjugation] = []
    gender: Optional[str] = None
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
