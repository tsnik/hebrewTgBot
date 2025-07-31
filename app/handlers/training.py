# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import (
    logger,
    TRAINING_MENU_STATE,
    FLASHCARD_SHOW,
    FLASHCARD_EVAL,
    AWAITING_VERB_ANSWER,
    VERB_TRAINER_NEXT_ACTION,
    CB_TRAIN_MENU,
    CB_TRAIN_HE_RU,
    CB_TRAIN_RU_HE,
    CB_VERB_TRAINER_START,
    CB_SHOW_ANSWER,
    CB_EVAL_CORRECT,
    CB_EVAL_INCORRECT,
    CB_END_TRAINING,
    CB_SETTINGS_MENU,
    VERB_TRAINER_RETRY_ATTEMPTS,
    PERSON_MAP,
    TENSE_MAP,
)
from dal.unit_of_work import UnitOfWork
from utils import normalize_hebrew, set_request_id
from metrics import increment_callbacks_counter, increment_messages_counter

# --- Вход в меню тренировок ---


@increment_callbacks_counter
@set_request_id
async def training_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отображает меню выбора режима тренировки."""
    query = update.callback_query

    keyboard = [
        [
            InlineKeyboardButton(
                "🇮🇱 → 🇷🇺 (Иврит → Русский)", callback_data=CB_TRAIN_HE_RU
            )
        ],
        [
            InlineKeyboardButton(
                "🇷🇺 → 🇮🇱 (Русский → Иврит)", callback_data=CB_TRAIN_RU_HE
            )
        ],
        [
            InlineKeyboardButton(
                "🔥 Глаголы (Спряжение)", callback_data=CB_VERB_TRAINER_START
            )
        ],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")],
    ]

    if query:
        await query.answer()
        await query.edit_message_text(
            text="Выберите режим тренировки:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите режим тренировки:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    return TRAINING_MENU_STATE


# --- Логика тренировки "Карточки" (Flashcards) ---


@increment_callbacks_counter
@set_request_id
async def start_flashcard_training(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Начинает тренировку с карточками."""
    query = update.callback_query
    await query.answer()
    context.user_data["training_mode"] = query.data

    with UnitOfWork() as uow:
        words = uow.user_dictionary.get_user_words_for_training(query.from_user.id, 10)

    if not words:
        await query.edit_message_text(
            "В словаре нет слов (существительных/прилагательных) для этой тренировки.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]]
            ),
        )
        return TRAINING_MENU_STATE

    context.user_data.update({"words": words, "idx": 0, "correct": 0})
    return await show_next_card(update, context)


async def show_next_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает следующую карточку в тренировке."""
    query = update.callback_query
    if query:
        await query.answer()

    idx = context.user_data.get("idx", 0)
    words = context.user_data.get("words", [])

    if idx >= len(words):
        await query.edit_message_text(
            f"Тренировка окончена!\n\nВаш результат: {context.user_data.get('correct', 0)} / {len(words)}",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "💪 Повторить",
                            callback_data=context.user_data["training_mode"],
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ В меню тренировок", callback_data=CB_TRAIN_MENU
                        )
                    ],
                ]
            ),
        )
        context.user_data.clear()
        return TRAINING_MENU_STATE

    word = words[idx]
    question = (
        word.hebrew
        if context.user_data["training_mode"] == CB_TRAIN_HE_RU
        else word.translations[0].translation_text
    )
    keyboard = [
        [InlineKeyboardButton("💡 Показать ответ", callback_data=CB_SHOW_ANSWER)],
        [InlineKeyboardButton("❌ Закончить", callback_data=CB_END_TRAINING)],
    ]

    message_text = f"Слово {idx + 1}/{len(words)}:\n\n*{question}*"
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(
            text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
        )

    return FLASHCARD_SHOW


@increment_callbacks_counter
@set_request_id
async def show_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает ответ на карточке."""
    query = update.callback_query
    await query.answer()

    word = context.user_data["words"][context.user_data["idx"]]
    answer_text = f"*{word.hebrew}* [{word.transcription}]\n\nПеревод: *{word.translations[0].translation_text}*"
    keyboard = [
        [InlineKeyboardButton("✅ Знаю", callback_data=CB_EVAL_CORRECT)],
        [InlineKeyboardButton("❌ Не знаю", callback_data=CB_EVAL_INCORRECT)],
    ]
    await query.edit_message_text(
        answer_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )
    return FLASHCARD_EVAL


@increment_callbacks_counter
@set_request_id
async def handle_self_evaluation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Обрабатывает самооценку пользователя (знаю/не знаю)."""
    query = update.callback_query
    word = context.user_data["words"][context.user_data["idx"]]

    with UnitOfWork() as uow:
        srs_level = uow.user_dictionary.get_srs_level(query.from_user.id, word.word_id)
        srs_level = srs_level if srs_level is not None else 0

        if query.data == CB_EVAL_CORRECT:
            context.user_data["correct"] += 1
            srs_level += 1
        else:
            srs_level = 0

        srs_intervals = [0, 1, 3, 7, 14, 30, 90]
        days_to_add = srs_intervals[min(srs_level, len(srs_intervals) - 1)]
        next_review_date = datetime.now() + timedelta(days=days_to_add)

        uow.user_dictionary.update_srs_level(
            srs_level, next_review_date, query.from_user.id, word.word_id
        )
        uow.commit()

    context.user_data["idx"] += 1
    return await show_next_card(update, context)


# --- Логика тренировки глаголов ---


@increment_callbacks_counter
@set_request_id
async def start_verb_trainer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает тренировку глаголов с учетом настроек пользователя."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    with UnitOfWork() as uow:
        user_settings = uow.user_settings.get_user_settings(user_id)
        if not user_settings.tense_settings:
            uow.user_settings.initialize_tense_settings(user_id)
            uow.commit()
            user_settings = uow.user_settings.get_user_settings(user_id)

        active_tenses = user_settings.get_active_tenses()

        if not active_tenses:
            keyboard = [
                [InlineKeyboardButton("⚙️ Настройки", callback_data=CB_SETTINGS_MENU)],
                [InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)],
            ]
            await query.edit_message_text(
                "Чтобы начать тренировку, выберите хотя бы одно время в разделе 'Настройки'.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return TRAINING_MENU_STATE

        verb, conjugation = None, None
        for i in range(VERB_TRAINER_RETRY_ATTEMPTS):
            verb_candidate = uow.words.get_random_verb_for_training(user_id)
            if not verb_candidate:
                await query.edit_message_text(
                    "В вашем словаре нет глаголов для тренировки.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]]
                    ),
                )
                return TRAINING_MENU_STATE

            conjugation_candidate = uow.words.get_random_conjugation_for_word(
                verb_candidate.word_id, active_tenses
            )
            if conjugation_candidate:
                verb, conjugation = verb_candidate, conjugation_candidate
                break
            else:
                logger.warning(
                    f"Не найдено спряжений в активных временах для глагола {verb_candidate.hebrew}. Попытка {i + 1}"
                )
    if not verb or not conjugation:
        logger.warning(
            f"Could not find a suitable verb for training for user after {VERB_TRAINER_RETRY_ATTEMPTS} retries."
        )
        await query.edit_message_text(
            "Не удалось найти подходящий глагол для тренировки. Возможно, для глаголов в вашем словаре нет спряжений в выбранных временах.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]]
            ),
        )
        return TRAINING_MENU_STATE

    context.user_data["answer"] = conjugation

    person_display = PERSON_MAP.get(conjugation.person.value, conjugation.person.value)
    tense_display = TENSE_MAP.get(
        conjugation.tense.value, conjugation.tense.value
    ).capitalize()

    question_text = f"Глагол: *{verb.hebrew}*\n\nНапишите его форму для:\n*{tense_display}, {person_display}*"
    await query.edit_message_text(question_text, parse_mode=ParseMode.MARKDOWN)

    return AWAITING_VERB_ANSWER


@increment_messages_counter
@set_request_id
async def check_verb_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Проверяет ответ пользователя в тренировке глаголов."""
    correct_answer = context.user_data.get("answer")
    if not correct_answer:
        return await training_menu(update, context)

    user_answer_normalized = normalize_hebrew(update.message.text)
    correct_answer_normalized = normalize_hebrew(correct_answer.hebrew_form)

    is_correct = user_answer_normalized == correct_answer_normalized
    logger.info(
        f"Verb training check. "
        f"User answer: '{user_answer_normalized}', "
        f"Correct answer: '{correct_answer_normalized}', "
        f"Result: {'CORRECT' if is_correct else 'INCORRECT'}"
    )

    if is_correct:
        reply_text = f"✅ Верно!\n\n*{correct_answer.hebrew_form}* [{correct_answer.transcription}]"
    else:
        reply_text = f"❌ Ошибка.\n\nПравильный ответ: *{correct_answer.hebrew_form}* [{correct_answer.transcription}]"

    with UnitOfWork() as uow:
        uow.user_dictionary.update_srs_level(
            0,
            datetime.now() + timedelta(days=1),
            update.effective_user.id,
            correct_answer.word_id,
        )
        uow.commit()

    keyboard = [
        [InlineKeyboardButton("🔥 Продолжить", callback_data=CB_VERB_TRAINER_START)],
        [InlineKeyboardButton("⬅️ В меню тренировок", callback_data=CB_TRAIN_MENU)],
    ]
    await update.message.reply_text(
        reply_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )

    return VERB_TRAINER_NEXT_ACTION


# --- Завершение тренировки ---


@increment_callbacks_counter
@set_request_id
async def end_training(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принудительно завершает любую тренировку."""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🇮🇱 → 🇷🇺 (Иврит → Русский)", callback_data=CB_TRAIN_HE_RU
            )
        ],
        [
            InlineKeyboardButton(
                "🇷🇺 → 🇮🇱 (Русский → Иврит)", callback_data=CB_TRAIN_RU_HE
            )
        ],
        [
            InlineKeyboardButton(
                "🔥 Глаголы (Спряжение)", callback_data=CB_VERB_TRAINER_START
            )
        ],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        text="Тренировка прервана. Выберите новый режим:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return TRAINING_MENU_STATE
