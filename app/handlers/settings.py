# -*- coding: utf-8 -*-

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import CB_SETTINGS_MENU, CB_TENSES_MENU, CB_TENSE_TOGGLE, TENSE_MAP
from dal.unit_of_work import UnitOfWork
from dal.models import Tense


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню настроек."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🕰️ Мои времена глаголов", callback_data=CB_TENSES_MENU)],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")],
    ]

    await query.edit_message_text(
        text="⚙️ Настройки", reply_markup=InlineKeyboardMarkup(keyboard)
    )


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


async def toggle_tense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает переключение статуса времени."""
    query = update.callback_query
    user_id = query.from_user.id
    tense_to_toggle = query.data.split(":")[2]

    with UnitOfWork() as uow:
        uow.user_settings.toggle_tense_setting(user_id, Tense(tense_to_toggle))
        uow.commit()

    # Обновляем меню, чтобы показать изменения
    await manage_tenses_menu(update, context)
