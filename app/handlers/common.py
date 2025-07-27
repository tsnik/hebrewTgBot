# -*- coding: utf-8 -*-

from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from config import (
    logger,
    CB_DICT_VIEW,
    CB_TRAIN_MENU,
    CB_ADD,
    CB_DICT_CONFIRM_DELETE,
    CB_SHOW_VERB,
)
from dal.unit_of_work import UnitOfWork


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user = update.effective_user
    with UnitOfWork() as uow:
        uow.user_dictionary.add_user(user.id, user.first_name, user.username)
        uow.commit()

    keyboard = [
        [InlineKeyboardButton("🧠 Мой словарь", callback_data=f"{CB_DICT_VIEW}:0")],
        [InlineKeyboardButton("💪 Тренировка", callback_data=CB_TRAIN_MENU)],
    ]
    await update.message.reply_text(
        f"Привет, {user.first_name}! Отправь мне слово на иврите для поиска.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возвращает пользователя в главное меню."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🧠 Мой словарь", callback_data=f"{CB_DICT_VIEW}:0")],
        [InlineKeyboardButton("💪 Тренировка", callback_data=CB_TRAIN_MENU)],
    ]
    await query.edit_message_text(
        "Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def display_word_card(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    word_data: dict,
    message_id: Optional[int] = None,
    in_dictionary: Optional[bool] = None,
):
    """
    Отображает карточку слова. Редактирует существующее сообщение, если
    передан message_id, иначе отправляет новое.
    """
    logger.info(f"-> display_word_card: Получены данные для карточки: {word_data}")

    word_id = word_data["word_id"]

    if in_dictionary is None:
        with UnitOfWork() as uow:
            in_dictionary = uow.user_dictionary.is_word_in_dictionary(user_id, word_id)

    translations = word_data.get("translations", [])
    primary_translation = next(
        (t.get("translation_text") for t in translations if t.get("is_primary")),
        "Перевод не найден",
    )
    other_translations = [
        t.get("translation_text") for t in translations if not t.get("is_primary")
    ]

    translation_str = primary_translation
    if other_translations:
        translation_str += f" (также: {', '.join(other_translations)})"

    card_text_header = (
        f"Слово *{word_data['hebrew']}* уже в вашем словаре."
        if in_dictionary
        else f"Найдено: *{word_data['hebrew']}*"
    )
    card_text = f"{card_text_header} [{word_data.get('transcription', '')}]\nПеревод: {translation_str}\n"

    # --- НОВАЯ ЛОГИКА ОТОБРАЖЕНИЯ ДАННЫХ ---
    pos = word_data.get("part_of_speech")
    if pos == "verb":
        if word_data.get("root"):
            card_text += f"\nКорень: {word_data['root']}"
        if word_data.get("binyan"):
            card_text += f"\nБиньян: {word_data['binyan']}"
    elif pos == "noun":
        if word_data.get("gender"):
            gender_display = (
                "Мужской род" if word_data["gender"] == "masculine" else "Женский род"
            )
            card_text += f"\nРод: {gender_display}"
        if word_data.get("singular_form"):
            card_text += f"\nЕд. число: {word_data['singular_form']}"
        if word_data.get("plural_form"):
            card_text += f"\nМн. число: {word_data['plural_form']}"
    elif pos == "adjective":
        card_text += "\n*Формы:*"
        if word_data.get("masculine_singular"):
            card_text += f"\nм.р., ед.ч.: {word_data['masculine_singular']}"
        if word_data.get("feminine_singular"):
            card_text += f"\nж.р., ед.ч.: {word_data['feminine_singular']}"
        if word_data.get("masculine_plural"):
            card_text += f"\nм.р., мн.ч.: {word_data['masculine_plural']}"
        if word_data.get("feminine_plural"):
            card_text += f"\nж.р., мн.ч.: {word_data['feminine_plural']}"

    card_text = card_text.strip()
    # --- КОНЕЦ НОВОЙ ЛОГИКИ ---

    keyboard_buttons = []
    if in_dictionary:
        # При переходе в режим удаления всегда открываем первую страницу
        keyboard_buttons.append(
            InlineKeyboardButton(
                "🗑️ Удалить", callback_data=f"{CB_DICT_CONFIRM_DELETE}:{word_id}:0"
            )
        )
    else:
        keyboard_buttons.append(
            InlineKeyboardButton("➕ Добавить", callback_data=f"{CB_ADD}:{word_id}")
        )

    # *** ИЗМЕНЕНА ПРОВЕРКА ***
    if word_data.get("part_of_speech") == "verb":
        keyboard_buttons.append(
            InlineKeyboardButton(
                "📖 Спряжения", callback_data=f"{CB_SHOW_VERB}:{word_id}"
            )
        )

    keyboard = [
        keyboard_buttons,
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=card_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=card_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
            )
    except Exception as e:
        if "Message is not modified" in str(e):
            logger.warning(
                "Попытка отредактировать сообщение без изменений. Игнорируется."
            )
        else:
            logger.error(
                f"Ошибка при отправке/редактировании карточки слова: {e}", exc_info=True
            )


async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершает диалог и возвращает в главное меню."""
    await main_menu(update, context)
    return ConversationHandler.END
