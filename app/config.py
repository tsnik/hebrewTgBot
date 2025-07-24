# -*- coding: utf-8 -*-

import os
import logging
from dotenv import load_dotenv

# --- ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
load_dotenv()

# --- КОНФИГУРАЦИЯ БОТА ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip("'\"")
DB_NAME = "data/hebrew_helper_cache.db"

# --- НАСТРОЙКИ ПАРСЕРА И БД ---
PARSING_TIMEOUT = 15
DB_READ_ATTEMPTS = 5
DB_READ_DELAY = 0.2
CONVERSATION_TIMEOUT_SECONDS = 1800  # 30 минут
VERB_TRAINER_RETRY_ATTEMPTS = 3
DICT_WORDS_PER_PAGE = 5  # <--- ДОБАВЛЕНА КОНСТАНТА

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- СОСТОЯНИЯ ДЛЯ CONVERSATION HANDLER ---
(
    TRAINING_MENU_STATE,
    FLASHCARD_SHOW,
    FLASHCARD_EVAL,
    AWAITING_VERB_ANSWER,
    VERB_TRAINER_NEXT_ACTION,
) = range(5)


# --- КОЛЛБЭК-ДАННЫЕ (CALLBACK DATA) --- ИЗМЕНЕНЫ НА ЧИТАЕМЫЕ
# Словарь
CB_DICT_VIEW = "dict:view"
CB_DICT_DELETE_MODE = "dict:delete_mode"
CB_DICT_CONFIRM_DELETE = "dict:confirm_delete"
CB_DICT_EXECUTE_DELETE = "dict:execute_delete"

# Карточка слова
CB_ADD = "word:add"
CB_SHOW_VERB = "verb:show"
CB_VIEW_CARD = "word:view"

# Меню тренировок
CB_TRAIN_MENU = "train:menu"
CB_TRAIN_HE_RU = "train:he_ru"
CB_TRAIN_RU_HE = "train:ru_he"
CB_VERB_TRAINER_START = "train:verb_start"

# Процесс тренировки
CB_SHOW_ANSWER = "train:show_answer"
CB_EVAL_CORRECT = "train:eval_correct"
CB_EVAL_INCORRECT = "train:eval_incorrect"
CB_END_TRAINING = "train:end"
