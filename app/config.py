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

# --- КОЛЛБЭК-ДАННЫЕ (CALLBACK DATA) ---
# Словарь
CB_DICT_VIEW = "d_v"
CB_DICT_DELETE_MODE = "d_dm"
CB_DICT_CONFIRM_DELETE = "d_cd"
CB_DICT_EXECUTE_DELETE = "d_ed"

# Карточка слова
CB_ADD = "add"
CB_SHOW_VERB = "sh_v"
CB_VIEW_CARD = "v_c"

# Меню тренировок
CB_TRAIN_MENU = "t_m"
CB_TRAIN_HE_RU = "t_hr"
CB_TRAIN_RU_HE = "t_rh"
CB_VERB_TRAINER_START = "vts"

# Процесс тренировки
CB_SHOW_ANSWER = "sh_a"
CB_EVAL_CORRECT = "e_c"
CB_EVAL_INCORRECT = "e_i"
CB_END_TRAINING = "e_t"