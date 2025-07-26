# -*- coding: utf-8 -*-

from __future__ import annotations
import abc
import sqlite3
from types import TracebackType
from typing import Optional, Type

from config import DB_NAME
from dal.repositories import WordRepository, UserDictionaryRepository

class AbstractUnitOfWork(abc.ABC):
    words: WordRepository
    user_dictionary: UserDictionaryRepository

    def __enter__(self) -> AbstractUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ):
        ...

    @abc.abstractmethod
    def commit(self):
        raise NotImplementedError

    @abc.abstractmethod
    def rollback(self):
        raise NotImplementedError


class UnitOfWork(AbstractUnitOfWork):
    def __init__(self, db_name: str = DB_NAME):
        self.db_name = db_name
        self.connection: Optional[sqlite3.Connection] = None

    def __enter__(self) -> AbstractUnitOfWork:
        self.connection = sqlite3.connect(self.db_name)
        self.connection.row_factory = sqlite3.Row
        self.words = WordRepository(self.connection)
        self.user_dictionary = UserDictionaryRepository(self.connection)
        return super().__enter__()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ):
        if exc_type:
            self.rollback()
        elif self.connection:
            self.commit()
        if self.connection:
            self.connection.close()

    def commit(self):
        if self.connection:
            self.connection.commit()

    def rollback(self):
        if self.connection:
            self.connection.rollback()
