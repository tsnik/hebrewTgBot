# -*- coding: utf-8 -*-

from __future__ import annotations
import abc
from types import TracebackType
from typing import Optional, Type

from config import logger
from dal.repositories import (
    WordRepository,
    UserDictionaryRepository,
    UserSettingsRepository,
)
from services.connection import Connection, db_manager


class AbstractUnitOfWork(abc.ABC):
    words: WordRepository
    user_dictionary: UserDictionaryRepository
    user_settings: UserSettingsRepository

    def __enter__(self) -> AbstractUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ): ...

    @abc.abstractmethod
    def commit(self):
        raise NotImplementedError

    @abc.abstractmethod
    def rollback(self):
        raise NotImplementedError


class UnitOfWork(AbstractUnitOfWork):
    def __init__(self):
        self.connection_manager = db_manager
        self.connection: Optional[Connection] = None
        self.is_postgres = self.connection_manager.is_postgres

    def __enter__(self) -> AbstractUnitOfWork:
        self.connection = self.connection_manager.__enter__()
        self.words = WordRepository(self.connection, self.is_postgres)
        self.user_dictionary = UserDictionaryRepository(
            self.connection, self.is_postgres
        )
        self.user_settings = UserSettingsRepository(self.connection, self.is_postgres)
        return super().__enter__()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ):
        if exc_type:
            logger.warning(
                "Exception occurred, rolling back transaction.", exc_info=True
            )
            self.rollback()
        elif self.connection:
            self.commit()
        self.connection_manager.__exit__(exc_type, exc_value, traceback)

    def commit(self):
        if self.connection:
            self.connection.commit()

    def rollback(self):
        if self.connection:
            self.connection.rollback()
