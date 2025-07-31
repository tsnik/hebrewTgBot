#!/bin/sh

# Останавливаем выполнение при любой ошибке
set -e

# --- Функция для логирования в формате JSON, совместимом с логами приложения ---
# Принимает два аргумента: 1 - Уровень лога (INFO, ERROR), 2 - Сообщение
log_json() {
  LOG_LEVEL=$1
  MESSAGE=$2
  # Создаем timestamp в формате "YYYY-MM-DD HH:MM:SS,ms", как у Python logging
  TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S,%3N")

  # Выводим однострочный JSON в stdout, соответствующий формату приложения
  echo "{\"asctime\": \"$TIMESTAMP\", \"name\": \"entrypoint\", \"levelname\": \"$LOG_LEVEL\", \"message\": \"$MESSAGE\"}"
}


log_json "INFO" "Starting container setup"

log_json "INFO" "Applying database migrations"
# Запускаем миграции. Если будет ошибка, `set -e` остановит скрипт.
# Вывод ошибки от yoyo будет захвачен Docker-ом как обычный текстовый лог,
# что поможет быстро идентифицировать проблему.
yoyo apply --no-config-file --database "sqlite:///data/hebrew_helper_cache.db" -v migrations

log_json "INFO" "Migrations applied successfully"

# exec "$@" выполняет команду из CMD Dockerfile.
log_json "INFO" "Handing over control to the main application"
exec "$@"