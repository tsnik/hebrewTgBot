#!/bin/bash

# Устанавливаем "ловушку": эта команда выполнится при любом выходе из скрипта
# Флаг -v говорит команде down также удалить все тома.
trap 'docker compose -f docker-compose.base.yml -f docker-compose.app.yml --profile tests down -v' EXIT

TEST_TO_RUN_LINE=""

if [ -n "$1" ]
then
TEST_TO_RUN_LINE="-e TEST_TO_RUN=tests/unit"
fi

echo "$TEST_TO_RUN_LINE"

# Команда собирает образы (если нужно), объединяет файлы,
# выбирает профиль "tests" и запускает сервис тестов.
docker compose -f docker-compose.base.yml -f docker-compose.app.yml --profile tests run --build $TEST_TO_RUN_LINE --rm tests