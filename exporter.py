import sqlite3
import time
from prometheus_client import start_http_server, Gauge

# --- Метрики, которые мы будем собирать ---
# Gauge - это метрика, значение которой может как увеличиваться, так и уменьшаться.
DB_USERS_TOTAL = Gauge("db_users_total", "Total number of users in the database")
DB_WORDS_TOTAL = Gauge("db_words_total", "Total number of cached words in the database")
DB_USER_DICTIONARY_ENTRIES_TOTAL = Gauge(
    "db_user_dictionary_entries_total", "Total number of words in all user dictionaries"
)

DATABASE_PATH = "/app/data/hebrew_helper_cache.db"


def query_database():
    """Подключается к БД и выполняет запросы."""
    try:
        # Используем read-only режим для безопасности
        con = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
        cur = con.cursor()

        # Запрос 1: Количество пользователей
        cur.execute("SELECT COUNT(*) FROM users")
        users_count = cur.fetchone()[0]
        DB_USERS_TOTAL.set(users_count)

        # Запрос 2: Количество слов в кэше
        cur.execute("SELECT COUNT(*) FROM cached_words")
        words_count = cur.fetchone()[0]
        DB_WORDS_TOTAL.set(words_count)

        # Запрос 3: Количество записей в словарях пользователей
        cur.execute("SELECT COUNT(*) FROM user_dictionary")
        dict_entries_count = cur.fetchone()[0]
        DB_USER_DICTIONARY_ENTRIES_TOTAL.set(dict_entries_count)

        con.close()
        print(
            f"Metrics updated: users={users_count}, words={words_count}, dict_entries={dict_entries_count}"
        )

    except Exception as e:
        print(f"Error querying database: {e}")


if __name__ == "__main__":
    # Запускаем HTTP-сервер для Prometheus на порту 9199
    start_http_server(9199)
    print("Exporter started on port 9199")

    # Бесконечный цикл для обновления метрик раз в 30 секунд
    while True:
        query_database()
        time.sleep(30)
