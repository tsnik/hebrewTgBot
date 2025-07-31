# Dockerfile для приложения "Помощник по ивриту"
# Автор: DevOps Инженер
# Версия: 1.2 (Исправлен формат ENV)

# --- Секция сборки ---
# 1. Используем официальный, легковесный образ Python
FROM python:3.10-slim-bookworm AS builder

# 2. Устанавливаем переменные окружения для лучшей практики
#    - не создавать .pyc файлы
#    - выводить логи напрямую, без буферизации
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# 4. Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Финальный образ ---
# Создаем новый "чистый" образ на той же основе
FROM python:3.10-slim-bookworm

WORKDIR /app

# Копируем установленные зависимости из образа-сборщика
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Установка curl для HEALTHCHECK
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Создаем директорию для хранения данных
RUN mkdir data

# Копируем код нашего приложения
COPY app/ .

# 6. Объявляем том для хранения персистентных данных (базы данных)
#    Это позволяет Docker управлять данными отдельно от контейнера.
VOLUME ["/app/data"]

# Добавление проверки состояния
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1

# 7. Указываем команду, которая будет выполняться при запуске контейнера
CMD ["sh", "-c", "echo '--- Starting container ---' && \
                  echo '--- Applying migrations... ---' && \
                  yoyo apply -v && \
                  echo '--- Migrations applied. Starting bot... ---' && \
                  python main.py"]
