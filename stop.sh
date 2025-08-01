#!/bin/bash

# Команда для остановки и удаления контейнеров,
# определенных в указанных файлах.
docker compose -f docker-compose.base.yml -f docker-compose.app.yml --profile=app down