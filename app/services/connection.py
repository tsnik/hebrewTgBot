# -*- coding: utf-8 -*-

import sqlite3
import threading
from types import TracebackType
from typing import Optional, Type

from config import DB_NAME

class DatabaseConnectionManager:
    def __init__(self, db_name: str, read_only: bool = True):
        self.db_name = db_name
        self.read_only = read_only
        self.connection: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()

    def __enter__(self) -> sqlite3.Connection:
        with self._lock:
            # For read-only connections, we can use a URI with `mode=ro`
            db_uri = f"file:{self.db_name}?mode=ro" if self.read_only else self.db_name
            try:
                self.connection = sqlite3.connect(db_uri, uri=True, check_same_thread=False)
                self.connection.row_factory = sqlite3.Row
            except sqlite3.OperationalError as e:
                # This can happen if the db doesn't exist yet and we're in read-only mode
                if "unable to open database file" in str(e) and self.read_only:
                    # Fallback to read-write mode to allow database creation
                    self.connection = sqlite3.connect(self.db_name, check_same_thread=False)
                    self.connection.row_factory = sqlite3.Row
                else:
                    raise e
            return self.connection

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

# Global connection managers
write_db_manager = DatabaseConnectionManager(DB_NAME, read_only=False)
read_db_manager = DatabaseConnectionManager(DB_NAME, read_only=True)
