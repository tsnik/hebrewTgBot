import os
import time
import psycopg2
from prometheus_client import start_http_server, Gauge

# --- Метрики, которые мы будем собирать ---
DB_USERS_TOTAL = Gauge("db_users_total", "Total number of users in the database")
DB_WORDS_TOTAL = Gauge("db_words_total", "Total number of cached words in the database")
DB_USER_DICTIONARY_ENTRIES_TOTAL = Gauge(
    "db_user_dictionary_entries_total", "Total number of words in all user dictionaries"
)

# Получаем строку подключения из переменной окружения
DATABASE_URL = os.getenv("DATABASE_URL")


def query_database():
    """Подключается к БД PostgreSQL и выполняет запросы."""
    if not DATABASE_URL:
        print("Error: DATABASE_URL environment variable is not set.")
        return

    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

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

        print(
            f"Metrics updated: users={users_count}, words={words_count}, dict_entries={dict_entries_count}"
        )

    except psycopg2.OperationalError as e:
        print(f"Error connecting to PostgreSQL database: {e}")
    except Exception as e:
        print(f"An error occurred while querying the database: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    # Запускаем HTTP-сервер для Prometheus на порту 9199
    start_http_server(9199)
    print("Exporter started on port 9199")

    # Бесконечный цикл для обновления метрик раз в 30 секунд
    while True:
        query_database()
        time.sleep(30)
