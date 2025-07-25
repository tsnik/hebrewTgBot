# -*- coding: utf-8 -*-

from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import (
    CB_DICT_VIEW, CB_DICT_DELETE_MODE, CB_DICT_CONFIRM_DELETE,
    CB_DICT_EXECUTE_DELETE, logger, DICT_WORDS_PER_PAGE
)
from dal.repositories import WordRepository, UserDictionaryRepository

word_repo = WordRepository()
user_dict_repo = UserDictionaryRepository()


async def view_dictionary_page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик кнопок для навигации по словарю и переключения
    в режим удаления.
    """
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split(':')
    action = f"{parts[0]}:{parts[1]}" # e.g., "dict:view"
    page = int(parts[2])
    # Определяем, был ли включен режим удаления
    deletion_mode = action == CB_DICT_DELETE_MODE
    
    await view_dictionary_page_logic(update, context, page=page, deletion_mode=deletion_mode)


async def view_dictionary_page_logic(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    deletion_mode: bool,
    exclude_word_id: Optional[int] = None
):
    """
    Основная логика для отображения страницы словаря.
    """
    query = update.callback_query
    user_id = query.from_user.id
    
    words_from_db = user_dict_repo.get_dictionary_page(user_id, page, DICT_WORDS_PER_PAGE)
    
    # Если мы только что удалили слово, убираем его из списка
    words = [w for w in words_from_db if w['word_id'] != exclude_word_id] if exclude_word_id else words_from_db
    
    has_next_page = len(words) > DICT_WORDS_PER_PAGE
    words_on_page = words[:DICT_WORDS_PER_PAGE]

    # Если страница пуста после удаления, переходим на предыдущую
    if not words_on_page and page > 0:
        return await view_dictionary_page_logic(update, context, page=page - 1, deletion_mode=False)
    
    # Если слов нет совсем
    if not words_on_page and page == 0:
        await query.edit_message_text(
            "Ваш словарь пуст.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")]])
        )
        return

    keyboard = []
    message_text = f"Ваш словарь (стр. {page + 1}):\n\n"
    if deletion_mode:
        message_text = "Выберите слово для удаления:"

    # Формируем список слов или кнопки для удаления
    for word in words_on_page:
        if deletion_mode:
            keyboard.append([
                InlineKeyboardButton(f"🗑️ {word['hebrew']}", callback_data=f"{CB_DICT_CONFIRM_DELETE}:{word['word_id']}:{page}")
            ])
        else:
            message_text += f"• {word['hebrew']} — {word['translation_text']}\n"
    
    # Навигационные кнопки
    nav_buttons = []
    nav_pattern = CB_DICT_DELETE_MODE if deletion_mode else CB_DICT_VIEW
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"{nav_pattern}:{page-1}"))
    if has_next_page:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"{nav_pattern}:{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопки управления
    if deletion_mode:
        keyboard.append([InlineKeyboardButton("⬅️ К словарю", callback_data=f"{CB_DICT_VIEW}:{page}")])
    else:
        # При переходе в режим удаления всегда открываем первую страницу
        keyboard.append([InlineKeyboardButton("🗑️ Удалить слово", callback_data=f"{CB_DICT_DELETE_MODE}:0")])
        keyboard.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")])
    
    await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def confirm_delete_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает подтверждение удаления слова."""
    query = update.callback_query
    await query.answer()
    
    _, _, word_id_str, page_str = query.data.split(':')
    word_hebrew = word_repo.get_word_hebrew_by_id(int(word_id_str))
    
    if not word_hebrew:
        await query.edit_message_text("Ошибка: слово не найдено.")
        return
        
    text = f"Вы уверены, что хотите удалить слово '{word_hebrew}' из вашего словаря?"
    keyboard = [
        [InlineKeyboardButton("✅ Да, удалить", callback_data=f"{CB_DICT_EXECUTE_DELETE}:{word_id_str}:{page_str}")],
        [InlineKeyboardButton("❌ Нет, отмена", callback_data=f"{CB_DICT_DELETE_MODE}:{page_str}")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def execute_delete_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Окончательно удаляет слово из словаря пользователя."""
    query = update.callback_query
    await query.answer("Слово удалено")
    
    _, _, word_id_str, page_str = query.data.split(':')
    word_id, page = int(word_id_str), int(page_str)
    
    user_dict_repo.remove_word_from_dictionary(query.from_user.id, word_id)
    
    # Перерисовываем страницу словаря, исключая удаленное слово
    await view_dictionary_page_logic(update, context, page=page, deletion_mode=False, exclude_word_id=word_id)
