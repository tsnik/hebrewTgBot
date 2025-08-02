# -*- coding: utf-8 -*-

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import (
    CB_SETTINGS_MENU,
    CB_TENSES_MENU,
    CB_TENSE_TOGGLE,
    TENSE_MAP,
    CB_TOGGLE_TRAINING_MODE,
    logger,
)
from dal.unit_of_work import UnitOfWork
from dal.models import Tense
from metrics import increment_callbacks_counter
from utils import set_request_id


@increment_callbacks_counter
@set_request_id
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню настроек."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # Получаем актуальные настройки пользователя
    with UnitOfWork() as uow:
        # Проверяем и при необходимости создаем записи в обеих таблицах настроек
        uow.user_settings.initialize_tense_settings(user_id)
        uow.user_settings.initialize_user_settings(user_id)
        uow.commit()

        user_settings = uow.user_settings.get_user_settings(user_id)

    mode_status = "✅ Вкл" if user_settings.use_grammatical_forms else "⬜️ Выкл"
    training_mode_button_text = f"🔄 Продвинутый режим: {mode_status}"

    keyboard = [
        [InlineKeyboardButton("🕰️ Мои времена глаголов", callback_data=CB_TENSES_MENU)],
        [
            InlineKeyboardButton(
                training_mode_button_text, callback_data=CB_TOGGLE_TRAINING_MODE
            )
        ],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")],
    ]

    message_text = (
        "⚙️ *Настройки*\n\n"
        "_В продвинутом режиме тренировки бот будет предлагать для запоминания случайные "
        "грамматические формы слов (число, род, спряжение), "
        "а не только их базовую форму._"
    )

    await query.edit_message_text(
        text=message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


@increment_callbacks_counter
@set_request_id
async def manage_tenses_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает меню управления временами глаголов."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    with UnitOfWork() as uow:
        # Инициализация настроек, если они отсутствуют
        user_settings = uow.user_settings.get_user_settings(user_id)
        if not user_settings.tense_settings:
            uow.user_settings.initialize_tense_settings(user_id)
            uow.commit()

        user_settings = uow.user_settings.get_user_settings(user_id)

    keyboard = []
    # Определяем нужный порядок времен
    tense_keys_ordered = ["perf", "ap", "impf", "imp"]

    # Создаем словарь из Pydantic моделей для быстрого доступа
    settings_map = user_settings.get_settings_as_dict()

    for tense_key in tense_keys_ordered:
        tense_name = TENSE_MAP.get(tense_key, tense_key)  # Используем TENSE_MAP
        is_active = settings_map.get(tense_key, False)
        status_icon = "✅" if is_active else "⬜️"
        button_text = f"{status_icon} {tense_name.capitalize()}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    button_text, callback_data=f"{CB_TENSE_TOGGLE}:{tense_key}"
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=CB_SETTINGS_MENU)])

    await query.edit_message_text(
        text="Выберите времена, которые вы хотите изучать и видеть в таблицах спряжений:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


@increment_callbacks_counter
@set_request_id
async def toggle_tense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает переключение статуса времени."""
    query = update.callback_query
    user_id = query.from_user.id
    tense_to_toggle = query.data.split(":")[2]

    with UnitOfWork() as uow:
        uow.user_settings.toggle_tense_setting(user_id, Tense(tense_to_toggle))

    logger.info(f"User {{user_id}} toggled tense '{tense_to_toggle}'.")

    # Обновляем меню, чтобы показать изменения
    await manage_tenses_menu(update, context)


@increment_callbacks_counter
@set_request_id
async def toggle_training_mode_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Обрабатывает переключение режима тренировки грамматических форм."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    with UnitOfWork() as uow:
        uow.user_settings.toggle_training_mode(user_id)
        uow.commit()

    # После изменения настройки, просто вызываем `settings_menu`,
    # чтобы перерисовать меню с актуальными данными.
    await settings_menu(update, context)
