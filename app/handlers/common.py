# -*- coding: utf-8 -*-

from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from config import logger, CB_DICT_VIEW, CB_TRAIN_MENU, CB_ADD, CB_DICT_CONFIRM_DELETE, CB_SHOW_VERB, CB_VIEW_CARD
from services.database import db_read_query, db_write_query


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user = update.effective_user
    # Добавляем пользователя в БД, если его там еще нет
    db_write_query(
        "INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
        (user.id, user.first_name, user.username)
    )
    keyboard = [
        [InlineKeyboardButton("🧠 Мой словарь", callback_data=f"{CB_DICT_VIEW}_0")],
        [InlineKeyboardButton("💪 Тренировка", callback_data=CB_TRAIN_MENU)]
    ]
    await update.message.reply_text(
        f"Привет, {user.first_name}! Отправь мне слово на иврите для поиска.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возвращает пользователя в главное меню."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🧠 Мой словарь", callback_data=f"{CB_DICT_VIEW}_0")],
        [InlineKeyboardButton("💪 Тренировка", callback_data=CB_TRAIN_MENU)]
    ]
    await query.edit_message_text(
        "Главное меню:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def display_word_card(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    word_data: dict,
    message_id: Optional[int] = None,
    in_dictionary: Optional[bool] = None  # <-- ИЗМЕНЕНИЕ: Добавлен новый параметр
):
    """
    Отображает карточку слова. Редактирует существующее сообщение, если
    передан message_id, иначе отправляет новое.
    """
    word_id = word_data['word_id']
    
    # --- НАЧАЛО ИЗМЕНЕНИЯ ---
    # Если статус не передан явно, проверяем его в БД.
    if in_dictionary is None:
        in_dictionary = db_read_query(
            "SELECT 1 FROM user_dictionary WHERE user_id = ? AND word_id = ?",
            (user_id, word_id),
            fetchone=True
        )
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    
    translations = word_data.get('translations', [])
    primary_translation = next((t['translation_text'] for t in translations if t['is_primary']), "Перевод не найден")
    other_translations = [t['translation_text'] for t in translations if not t['is_primary']]
    
    translation_str = primary_translation
    if other_translations:
        translation_str += f" (также: {', '.join(other_translations)})"

    card_text_header = f"Слово *{word_data['hebrew']}* уже в вашем словаре." if in_dictionary else f"Найдено: *{word_data['hebrew']}*"
    card_text = f"{card_text_header} [{word_data.get('transcription', '')}]\nПеревод: {translation_str}"

    keyboard_buttons = []
    if in_dictionary:
        keyboard_buttons.append(InlineKeyboardButton("🗑️ Удалить", callback_data=f"{CB_DICT_CONFIRM_DELETE}_{word_id}_0"))
    else:
        keyboard_buttons.append(InlineKeyboardButton("➕ Добавить", callback_data=f"{CB_ADD}_{word_id}"))

    if word_data.get('is_verb'):
        keyboard_buttons.append(InlineKeyboardButton("📖 Спряжения", callback_data=f"{CB_SHOW_VERB}_{word_id}"))
    
    keyboard = [keyboard_buttons, [InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=card_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=card_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    except Exception as e:
        # Проверяем на ошибку "Message is not modified" и игнорируем ее
        if "Message is not modified" in str(e):
            logger.warning("Попытка отредактировать сообщение без изменений. Игнорируется.")
        else:
            logger.error(f"Ошибка при отправке/редактировании карточки слова: {e}", exc_info=True)


async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершает диалог и возвращает в главное меню."""
    await main_menu(update, context)
    return ConversationHandler.END
