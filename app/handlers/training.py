# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from ..config import (
    logger,
    TRAINING_MENU_STATE, FLASHCARD_SHOW, FLASHCARD_EVAL,
    AWAITING_VERB_ANSWER, VERB_TRAINER_NEXT_ACTION,
    CB_TRAIN_MENU, CB_TRAIN_HE_RU, CB_TRAIN_RU_HE, CB_VERB_TRAINER_START,
    CB_SHOW_ANSWER, CB_EVAL_CORRECT, CB_EVAL_INCORRECT, CB_END_TRAINING,
    VERB_TRAINER_RETRY_ATTEMPTS
)
from ..services.database import db_read_query, db_write_query
from ..utils import normalize_hebrew
from .common import main_menu

# --- Вход в меню тренировок ---

async def training_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отображает меню выбора режима тренировки."""
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("🇮🇱 → 🇷🇺 (Иврит → Русский)", callback_data=CB_TRAIN_HE_RU)],
        [InlineKeyboardButton("🇷🇺 → 🇮🇱 (Русский → Иврит)", callback_data=CB_TRAIN_RU_HE)],
        [InlineKeyboardButton("🔥 Глаголы (Спряжение)", callback_data=CB_VERB_TRAINER_START)],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")]
    ]
    
    # --- НАЧАЛО ИЗМЕНЕНИЯ ---
    # Разделяем логику для редактирования и отправки нового сообщения
    if query:
        await query.answer()
        await query.edit_message_text(
            text="Выберите режим тренировки:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # Этот блок кода может понадобиться, если мы будем вызывать
        # training_menu не через кнопку, а командой.
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите режим тренировки:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
        
    return TRAINING_MENU_STATE

# --- Логика тренировки "Карточки" (Flashcards) ---

async def start_flashcard_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает тренировку с карточками."""
    query = update.callback_query
    await query.answer()
    context.user_data['training_mode'] = query.data
    
    sql_query = """
        SELECT cw.*, t.translation_text
        FROM cached_words cw
        JOIN user_dictionary ud ON cw.word_id = ud.word_id
        JOIN translations t ON cw.word_id = t.word_id
        WHERE ud.user_id = ? AND cw.is_verb = 0 AND t.is_primary = 1
        ORDER BY ud.next_review_at ASC LIMIT 10
    """
    words = db_read_query(sql_query, (query.from_user.id,), fetchall=True)

    if not words:
        await query.edit_message_text(
            "В словаре нет слов (существительных/прилагательных) для этой тренировки.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]])
        )
        return TRAINING_MENU_STATE

    context.user_data.update({'words': [dict(w) for w in words], 'idx': 0, 'correct': 0})
    return await show_next_card(update, context)


async def show_next_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает следующую карточку в тренировке."""
    query = update.callback_query
    if query:
        await query.answer()
    
    idx = context.user_data.get('idx', 0)
    words = context.user_data.get('words', [])

    if idx >= len(words):
        await query.edit_message_text(
            f"Тренировка окончена!\n\nВаш результат: {context.user_data.get('correct', 0)} / {len(words)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💪 Повторить", callback_data=context.user_data['training_mode'])],
                [InlineKeyboardButton("⬅️ В меню тренировок", callback_data=CB_TRAIN_MENU)]
            ])
        )
        context.user_data.clear()
        return TRAINING_MENU_STATE

    word = words[idx]
    question = word['hebrew'] if context.user_data['training_mode'] == CB_TRAIN_HE_RU else word['translation_text']
    keyboard = [
        [InlineKeyboardButton("💡 Показать ответ", callback_data=CB_SHOW_ANSWER)],
        [InlineKeyboardButton("❌ Закончить", callback_data=CB_END_TRAINING)]
    ]
    
    message_text = f"Слово {idx + 1}/{len(words)}:\n\n*{question}*"
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    return FLASHCARD_SHOW


async def show_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает ответ на карточке."""
    query = update.callback_query
    await query.answer()

    word = context.user_data['words'][context.user_data['idx']]
    answer_text = f"*{word['hebrew']}* [{word['transcription']}]\n\nПеревод: *{word['translation_text']}*"
    keyboard = [
        [InlineKeyboardButton("✅ Знаю", callback_data=CB_EVAL_CORRECT)],
        [InlineKeyboardButton("❌ Не знаю", callback_data=CB_EVAL_INCORRECT)]
    ]
    await query.edit_message_text(answer_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return FLASHCARD_EVAL


async def handle_self_evaluation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает самооценку пользователя (знаю/не знаю)."""
    query = update.callback_query
    word = context.user_data['words'][context.user_data['idx']]
    
    srs_data = db_read_query("SELECT srs_level FROM user_dictionary WHERE user_id = ? AND word_id = ?", (query.from_user.id, word['word_id']), fetchone=True)
    srs_level = srs_data['srs_level'] if srs_data else 0

    if query.data == CB_EVAL_CORRECT:
        context.user_data['correct'] += 1
        srs_level += 1
    else:
        srs_level = 0
    
    srs_intervals = [0, 1, 3, 7, 14, 30, 90]
    days_to_add = srs_intervals[min(srs_level, len(srs_intervals) - 1)]
    next_review_date = datetime.now() + timedelta(days=days_to_add)

    db_write_query(
        "UPDATE user_dictionary SET srs_level = ?, next_review_at = ? WHERE user_id = ? AND word_id = ?",
        (srs_level, next_review_date, query.from_user.id, word['word_id'])
    )

    context.user_data['idx'] += 1
    return await show_next_card(update, context)


# --- Логика тренировки глаголов ---

async def start_verb_trainer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает тренировку глаголов."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    verb, conjugation = None, None

    for i in range(VERB_TRAINER_RETRY_ATTEMPTS):
        verb_candidate = db_read_query(
            "SELECT cw.* FROM cached_words cw JOIN user_dictionary ud ON cw.word_id = ud.word_id WHERE ud.user_id = ? AND cw.is_verb = 1 ORDER BY RANDOM() LIMIT 1",
            (user_id,), fetchone=True
        )
        if not verb_candidate:
            await query.edit_message_text(
                "В вашем словаре нет глаголов для тренировки.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]])
            )
            return TRAINING_MENU_STATE

        conjugation_candidate = db_read_query("SELECT * FROM verb_conjugations WHERE word_id = ? ORDER BY RANDOM() LIMIT 1", (verb_candidate['word_id'],), fetchone=True)
        if conjugation_candidate:
            verb, conjugation = verb_candidate, conjugation_candidate
            break
        else:
            logger.warning(f"Ошибка целостности данных: у глагола {verb_candidate['hebrew']} (id: {verb_candidate['word_id']}) нет спряжений. Попытка {i+1}/{VERB_TRAINER_RETRY_ATTEMPTS}")

    if not verb or not conjugation:
        await query.edit_message_text(
            "Не удалось найти подходящий глагол для тренировки. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]])
        )
        return TRAINING_MENU_STATE

    context.user_data['answer'] = dict(conjugation)
    
    question_text = f"Глагол: *{verb['hebrew']}*\n\nНапишите его форму для:\n*{conjugation['tense']}, {conjugation['person']}*"
    await query.edit_message_text(question_text, parse_mode=ParseMode.MARKDOWN)
    
    return AWAITING_VERB_ANSWER


async def check_verb_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет ответ пользователя в тренировке глаголов."""
    correct_answer = context.user_data.get('answer')
    if not correct_answer:
        return await training_menu(update, context)

    user_answer_normalized = normalize_hebrew(update.message.text)
    correct_answer_normalized = normalize_hebrew(correct_answer['hebrew_form'])
    
    if user_answer_normalized == correct_answer_normalized:
        reply_text = f"✅ Верно!\n\n*{correct_answer['hebrew_form']}* [{correct_answer['transcription']}]"
    else:
        reply_text = f"❌ Ошибка.\n\nПравильный ответ: *{correct_answer['hebrew_form']}* [{correct_answer['transcription']}]"
    
    db_write_query(
        "UPDATE user_dictionary SET next_review_at = ? WHERE user_id = ? AND word_id = ?",
        (datetime.now() + timedelta(days=1), update.effective_user.id, correct_answer['word_id'])
    )
    
    keyboard = [
        [InlineKeyboardButton("🔥 Продолжить", callback_data=CB_VERB_TRAINER_START)],
        [InlineKeyboardButton("⬅️ В меню тренировок", callback_data=CB_TRAIN_MENU)]
    ]
    await update.message.reply_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    
    return VERB_TRAINER_NEXT_ACTION


# --- Завершение тренировки ---

async def end_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принудительно завершает любую тренировку."""
    query = update.callback_query
    await query.answer()

    # --- НАЧАЛО ИЗМЕНЕНИЯ ---
    # Вместо вызова training_menu, сразу редактируем сообщение, показывая меню.
    # Это более чистое решение.
    keyboard = [
        [InlineKeyboardButton("🇮🇱 → 🇷🇺 (Иврит → Русский)", callback_data=CB_TRAIN_HE_RU)],
        [InlineKeyboardButton("🇷🇺 → 🇮🇱 (Русский → Иврит)", callback_data=CB_TRAIN_RU_HE)],
        [InlineKeyboardButton("🔥 Глаголы (Спряжение)", callback_data=CB_VERB_TRAINER_START)],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")]
    ]
    await query.edit_message_text(
        text="Тренировка прервана. Выберите новый режим:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    
    return TRAINING_MENU_STATE
