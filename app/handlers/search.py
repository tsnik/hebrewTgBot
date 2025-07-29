# -*- coding: utf-8 -*-
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import (
    CB_VIEW_CARD,
    CB_SEARCH_PEALIM,
    CB_SELECT_WORD,
    CB_SHOW_ALL_VERB_FORMS,
    PERSON_MAP,
    TENSE_MAP,
    logger,
)
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
        # Используем новый метод, возвращающий список
        found_words = uow.words.find_words_by_normalized_form(normalized_text)

    # Случай 1.1: Нет совпадений в локальной БД
    if not found_words:
        await search_in_pealim(update, context, normalized_text)
        return

    # Случай 1.2: Одно совпадение
    if len(found_words) == 1:
        word_data = found_words[0]
        await display_word_card(
            context,
            user_id,
            chat_id,
            word_data,
            show_pealim_search_button=True,  # Показываем кнопку
            search_query=normalized_text,
        )
        return

    # Случай 1.3: Несколько совпадений
    if len(found_words) > 1:
        message_text = "Найдено несколько вариантов. Выберите нужный:"
        keyboard = []
        for word in found_words:
            primary_translation = next(
                (t.translation_text for t in word.translations if t.is_primary), ""
            )
            button_text = f"{word.hebrew} - {primary_translation}"
            # Используем новую константу для callback
            keyboard.append(
                [
                    InlineKeyboardButton(
                        button_text,
                        callback_data=f"{CB_SELECT_WORD}:{word.word_id}:{normalized_text}",
                    )
                ]
            )

        # Добавляем кнопку поиска в Pealim
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔎 Искать еще в Pealim",
                    callback_data=f"{CB_SEARCH_PEALIM}:{normalized_text}",
                )
            ]
        )

        await update.message.reply_text(
            message_text, reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def search_in_pealim(
    update: Update, context: ContextTypes.DEFAULT_TYPE, query: str
):
    """Выполняет поиск слова во внешнем источнике."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Проверяем, было ли сообщение от пользователя или это callback
    if update.message:
        status_message = await update.message.reply_text(
            "🔎 Ищу слово во внешнем словаре..."
        )
        message_id = status_message.message_id
    else:  # Если это callback_query
        await update.callback_query.answer()
        # Редактируем сообщение, с которого пришел callback
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=update.callback_query.message.message_id,
            text="🔎 Ищу слово во внешнем словаре...",
        )
        message_id = update.callback_query.message.message_id

    status, data_list = await fetch_and_cache_word_data(query)

    if status == "ok" and data_list:
        if len(data_list) == 1:
            await display_word_card(
                context, user_id, chat_id, data_list[0], message_id=message_id
            )
        else:
            message_text = (
                "Во внешнем источнике найдено несколько вариантов. Выберите нужный:"
            )
            keyboard = []
            for word in data_list:
                primary_translation = word.translations[0].translation_text
                button_text = f"{word.hebrew} - {primary_translation}"
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            button_text,
                            # Важно! Используем word_id, который был присвоен при сохранении в БД
                            callback_data=f"{CB_SELECT_WORD}:{word.word_id}:{query}",
                        )
                    ]
                )

            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
    elif status == "not_found":
        await context.bot.edit_message_text(
            f"Слово '{query}' не найдено.",
            chat_id=chat_id,
            message_id=message_id,
        )
    elif status == "error":
        await context.bot.edit_message_text(
            "Внешний сервис словаря временно недоступен. Попробуйте, пожалуйста, позже.",
            chat_id=chat_id,
            message_id=message_id,
        )
    elif status == "db_error":
        await context.bot.edit_message_text(
            "Произошла внутренняя ошибка при сохранении слова. Пожалуйста, попробуйте позже.",
            chat_id=chat_id,
            message_id=message_id,
        )


async def pealim_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки 'Искать еще в Pealim'."""
    query_data = update.callback_query.data.split(":")
    search_query = query_data[2]
    await search_in_pealim(update, context, search_query)


async def select_word_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора одного из нескольких найденных слов."""
    query = update.callback_query
    await query.answer()

    logger.info(query.data)

    _, _, word_id_str, search_query = query.data.split(":")
    word_id = int(word_id_str)

    user_id = query.from_user.id
    chat_id = query.message.chat_id

    with UnitOfWork() as uow:
        word_data = uow.words.get_word_by_id(word_id)

    if word_data:
        await display_word_card(
            context,
            user_id,
            chat_id,
            word_data,
            message_id=query.message.message_id,
            show_pealim_search_button=True,  # Также показываем кнопку
            search_query=search_query,
        )
    else:
        # Обработка ошибки, если слово не найдено
        await query.edit_message_text("Ошибка: не удалось найти выбранное слово.")


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
        word_dict = word_data
        await display_word_card(
            context,
            user_id,
            query.message.chat_id,
            word_dict,
            message_id=query.message.message_id,
            in_dictionary=True,
        )


async def show_verb_conjugations(
    update: Update, context: ContextTypes.DEFAULT_TYPE, show_all: bool = False
):
    """Показывает таблицу спряжений для глагола с учетом настроек пользователя."""
    query = update.callback_query
    await query.answer()

    word_id = int(query.data.split(":")[-1])
    user_id = query.from_user.id

    with UnitOfWork() as uow:
        word_hebrew = uow.words.get_word_hebrew_by_id(word_id)
        all_conjugations = uow.words.get_conjugations_for_word(word_id)

        user_settings = uow.user_settings.get_user_settings(user_id)
        # Инициализация, если настроек нет
        if not user_settings.tense_settings:
            uow.user_settings.initialize_tense_settings(user_id)
            uow.commit()
            user_settings = uow.user_settings.get_user_settings(user_id)

        active_tenses = user_settings.get_active_tenses()

    keyboard = [
        [
            InlineKeyboardButton(
                "⬅️ Назад к слову", callback_data=f"{CB_VIEW_CARD}:{word_id}"
            )
        ]
    ]

    if not all_conjugations or not word_hebrew:
        await query.edit_message_text(
            "Для этого глагола нет таблицы спряжений.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # Разделяем спряжения на активные и скрытые
    active_conjugations = [
        c for c in all_conjugations if c.tense.value in active_tenses
    ]
    hidden_conjugations = [
        c for c in all_conjugations if c.tense.value not in active_tenses
    ]

    conjugations_to_display = all_conjugations if show_all else active_conjugations

    message_text = f"Спряжения для *{word_hebrew}*:\n"

    if not conjugations_to_display and not show_all:
        message_text = "Все времена скрыты. Включите их в разделе 'Настройки', чтобы увидеть спряжения по умолчанию."
    else:
        # Группируем по времени
        conjugations_by_tense = {}
        for conj in conjugations_to_display:
            tense_val = conj.tense.value
            if tense_val not in conjugations_by_tense:
                conjugations_by_tense[tense_val] = []
            conjugations_by_tense[tense_val].append(conj)

        for tense, conj_list in sorted(
            conjugations_by_tense.items(),
            key=lambda item: list(TENSE_MAP.keys()).index(item[0]),
        ):
            tense_display = TENSE_MAP.get(tense, tense)
            message_text += f"\n*{tense_display.capitalize()}*:\n"
            for conj in conj_list:
                person_display = PERSON_MAP.get(conj.person.value, conj.person.value)
                message_text += (
                    f"_{person_display}_: {conj.hebrew_form} ({conj.transcription})\n"
                )

    # Добавляем кнопку "Показать остальные", если нужно
    if not show_all and hidden_conjugations:
        keyboard.insert(
            0,
            [
                InlineKeyboardButton(
                    "👁️ Показать остальные времена",
                    callback_data=f"{CB_SHOW_ALL_VERB_FORMS}:{word_id}",
                )
            ],
        )

    if len(message_text) > 4096:
        message_text = message_text[:4090] + "\n(...)"

    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


async def show_all_verb_forms_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Обработчик для кнопки 'Показать остальные времена'."""
    await show_verb_conjugations(update, context, show_all=True)


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
        word_dict = word_data
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
