# -*- coding: utf-8 -*-
import asyncio
import re
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import logger, CB_ADD, CB_SHOW_VERB, CB_VIEW_CARD
from services.parser import fetch_and_cache_word_data
from utils import normalize_hebrew
from handlers.common import display_word_card
from dal.unit_of_work import UnitOfWork


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик текстовых сообщений для поиска слов."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not re.match(r"^[\u0590-\u05FF\s-]+$", text):
        await update.message.reply_text(
            "Пожалуйста, используйте только буквы иврита, пробелы и дефисы."
        )
        return
    if len(text.split()) > 1:
        await update.message.reply_text(
            "Пожалуйста, отправляйте только по одному слову за раз."
        )
        return

    normalized_text = normalize_hebrew(text)

    with UnitOfWork() as uow:
        word_data = uow.words.find_word_by_normalized_form(normalized_text)
        if word_data:
            word_dict = word_data.model_dump()
            await display_word_card(context, user_id, chat_id, word_dict)
            return

    status_message = await update.message.reply_text(
        "🔎 Ищу слово во внешнем словаре..."
    )

    status, data = await fetch_and_cache_word_data(text)

    if status == "ok" and data:
        await display_word_card(
            context,
            user_id,
            chat_id,
            word_data=data,
            message_id=status_message.message_id,
        )
    elif status == "not_found":
        await context.bot.edit_message_text(
            f"Слово '{text}' не найдено.",
            chat_id=chat_id,
            message_id=status_message.message_id,
        )
    elif status == "error":
        await context.bot.edit_message_text(
            "Внешний сервис словаря временно недоступен. Попробуйте, пожалуйста, позже.",
            chat_id=chat_id,
            message_id=status_message.message_id,
        )
    elif status == "db_error":
        await context.bot.edit_message_text(
            "Произошла внутренняя ошибка при сохранении слова. Пожалуйста, попробуйте позже.",
            chat_id=chat_id,
            message_id=status_message.message_id,
        )


async def add_word_to_dictionary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия кнопки 'Добавить'."""
    query = update.callback_query
    await query.answer("Добавлено!")

    word_id = int(query.data.split(":")[2])
    user_id = query.from_user.id

    with UnitOfWork() as uow:
        uow.user_dictionary.add_word_to_dictionary(user_id, word_id)
        uow.commit()
        word_data = uow.words.get_word_by_id(word_id)

    if word_data:
        word_dict = word_data.model_dump()
        await display_word_card(
            context,
            user_id,
            query.message.chat_id,
            word_dict,
            message_id=query.message.message_id,
            in_dictionary=True,
        )


async def show_verb_conjugations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает таблицу спряжений для глагола."""
    query = update.callback_query
    await query.answer()

    word_id = int(query.data.split(":")[-1])
    with UnitOfWork() as uow:
        word_hebrew = uow.words.get_word_hebrew_by_id(word_id)
        conjugations = uow.words.get_conjugations_for_word(word_id)

    keyboard = [
        [
            InlineKeyboardButton(
                "⬅️ Назад к слову", callback_data=f"{CB_VIEW_CARD}:{word_id}"
            )
        ]
    ]

    if not conjugations or not word_hebrew:
        await query.edit_message_text(
            "Для этого глагола нет таблицы спряжений.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    conjugations_by_tense = {}
    message_text = f"Спряжения для *{word_hebrew}*:\n"

    for conj in conjugations:
        if conj.tense not in conjugations_by_tense:
            conjugations_by_tense[conj.tense] = []
        conjugations_by_tense[conj.tense].append(conj)

    for tense, conj_list in conjugations_by_tense.items():
        message_text += f"\n*{tense.capitalize()}*:\n"
        for conj in conj_list:
            message_text += (
                f"_{conj.person}_: {conj.hebrew_form} ({conj.transcription})\n"
            )

    if len(message_text) > 4096:
        message_text = message_text[:4090] + "\n(...)"

    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


async def view_word_card_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для возврата к карточке слова (например, со страницы спряжений)."""
    query = update.callback_query
    await query.answer()

    word_id = int(query.data.split(":")[-1])
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    with UnitOfWork() as uow:
        word_data = uow.words.get_word_by_id(word_id)

    if word_data:
        word_dict = word_data.model_dump()
        await display_word_card(
            context, user_id, chat_id, word_data=word_dict, message_id=message_id
        )
    else:
        await query.edit_message_text(
            "Ошибка: слово не найдено.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")]]
            ),
        )
