#!/bin/bash

# Эта команда объединяет базовый и основной compose-файлы,
# выбирает профиль "app" и запускает все в фоновом режиме.
docker compose \
  -f docker-compose.base.yml \
  -f docker-compose.app.yml \
  --profile app \
  up -d --build