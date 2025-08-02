# -*- coding: utf-8 -*-

import os
import logging
from dotenv import load_dotenv
from pythonjsonlogger import jsonlogger
from context import RequestIdFilter

# --- ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
load_dotenv()

# --- КОНФИГУРАЦИЯ БОТА ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", None)
DB_NAME = "data/hebrew_helper_cache.db"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/hebrew_helper_cache.db")

# --- НАСТРОЙКИ ПАРСЕРА И БД ---
PARSING_TIMEOUT = 15
DB_READ_ATTEMPTS = 5
DB_READ_DELAY = 0.2
CONVERSATION_TIMEOUT_SECONDS = 1800  # 30 минут
VERB_TRAINER_RETRY_ATTEMPTS = 3
DICT_WORDS_PER_PAGE = 5  # <--- ДОБАВЛЕНА КОНСТАНТА

# --- НАСТРОЙКА ЛОГИРОВАНИЯ ---

request_id_filter = RequestIdFilter()

LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = logging.getLevelName(LOG_LEVEL_NAME)
if not isinstance(LOG_LEVEL, int):
    print(f"Warning: Invalid log level '{LOG_LEVEL_NAME}'. Defaulting to INFO.")
    LOG_LEVEL = logging.INFO
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    "%(asctime)s %(name)s %(levelname)s %(message)s", json_ensure_ascii=False
)
logHandler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(logHandler)
logger.setLevel(LOG_LEVEL)
logger.addFilter(request_id_filter)
logger.info(f"Logging level set to {LOG_LEVEL_NAME}")
logging.getLogger("httpx").setLevel(logging.WARNING)


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
CB_SELECT_WORD = "word:select"
CB_SEARCH_PEALIM = "word:search_pealim"
CB_SHOW_ALL_VERB_FORMS = "verb:show_all"

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

# Настройки
CB_SETTINGS_MENU = "settings:menu"
CB_TENSES_MENU = "settings:tenses_menu"
CB_TENSE_TOGGLE = "settings:tense_toggle"
CB_TOGGLE_TRAINING_MODE = "settings:toggle_training_mode"


# ДОБАВЛЕН СЛОВАРЬ ДЛЯ ОТОБРАЖЕНИЯ ЛИЦ
PERSON_MAP = {
    "1s": "1 л., ед.ч. (я)",
    "1p": "1 л., мн.ч. (мы)",
    "2ms": "2 л., м.р., ед.ч. (ты)",
    "2fs": "2 л., ж.р., ед.ч. (ты)",
    "2mp": "2 л., м.р., мн.ч. (вы)",
    "2fp": "2 л., ж.р., мн.ч. (вы)",
    "3ms": "3 л., м.р., ед.ч. (он)",
    "3fs": "3 л., ж.р., ед.ч. (она)",
    "3p": "3 л., мн.ч. (они)",
    "3fp": "3 л., ж.р., мн.ч. (они)",
    "3mp": "3 л., м.р., мн.ч. (они)",
    # Для форм настоящего времени, где нет стандартного лица
    "ms": "м.р., ед.ч.",
    "fs": "ж.р., ед.ч.",
    "mp": "м.р., мн.ч.",
    "fp": "ж.р., мн.ч.",
}


TENSE_MAP = {
    "ap": "настоящее",
    "perf": "прошедшее",
    "impf": "будущее",
    "imp": "повелительное",
    "inf": "инфинитив",
}


BINYAN_MAP = {
    "paal": "пааль",
    "piel": "пиэль",
    "nifal": "нифъаль",
    "hifil": "хифъиль",
    "hitpael": "хитпаэль",
    "pual": "пуаль",
    "hufal": "хуфъаль",
}
