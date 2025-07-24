# -*- coding: utf-8 -*-

import sys
import threading
import asyncio

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config import (
    BOT_TOKEN, logger, CONVERSATION_TIMEOUT_SECONDS,
    TRAINING_MENU_STATE, FLASHCARD_SHOW, FLASHCARD_EVAL,
    AWAITING_VERB_ANSWER, VERB_TRAINER_NEXT_ACTION,
    CB_DICT_VIEW, CB_DICT_DELETE_MODE, CB_DICT_CONFIRM_DELETE,
    CB_DICT_EXECUTE_DELETE, CB_ADD, CB_SHOW_VERB, CB_VIEW_CARD,
    CB_TRAIN_MENU, CB_TRAIN_HE_RU, CB_TRAIN_RU_HE, CB_VERB_TRAINER_START,
    CB_SHOW_ANSWER, CB_EVAL_CORRECT, CB_EVAL_INCORRECT, CB_END_TRAINING
)

# Импортируем сервисы
from services.database import init_db, db_worker, DB_WRITE_QUEUE

# Импортируем обработчики
from handlers.common import start, main_menu, back_to_main_menu
from handlers.search import (
    handle_text_message, add_word_to_dictionary,
    show_verb_conjugations, view_word_card_handler
)
from handlers.dictionary import (
    view_dictionary_page_handler, confirm_delete_word, execute_delete_word
)
from handlers.training import (
    training_menu, start_flashcard_training, show_next_card,
    show_answer, handle_self_evaluation, start_verb_trainer,
    check_verb_answer, end_training
)


def main() -> None:
    """Основная функция для запуска бота."""
    if not BOT_TOKEN:
        logger.critical("Токен бота не найден. Укажите TELEGRAM_BOT_TOKEN в .env файле.")
        sys.exit("Токен не найден.")

    # 1. Запускаем воркер для записи в БД в отдельном потоке
    db_worker_thread = threading.Thread(target=db_worker, daemon=True)
    db_worker_thread.start()
    
    # 2. Инициализируем таблицы в БД
    init_db()
    
    # 3. Собираем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # 4. Настраиваем ConversationHandler для тренировок
    conv_defaults = {
        "per_user": True,
        "per_chat": True,
        "conversation_timeout": CONVERSATION_TIMEOUT_SECONDS
    }

    training_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(training_menu, pattern=f"^{CB_TRAIN_MENU}$")],
        states={
            TRAINING_MENU_STATE: [
                CallbackQueryHandler(training_menu, pattern=f"^{CB_TRAIN_MENU}$"),
                CallbackQueryHandler(start_flashcard_training, pattern=f"^({CB_TRAIN_HE_RU}|{CB_TRAIN_RU_HE})$"),
                CallbackQueryHandler(start_verb_trainer, pattern=f"^{CB_VERB_TRAINER_START}$"),
                CallbackQueryHandler(back_to_main_menu, pattern="^main_menu$")
            ],
            FLASHCARD_SHOW: [
                CallbackQueryHandler(show_answer, pattern=f"^{CB_SHOW_ANSWER}$"),
                CallbackQueryHandler(end_training, pattern=f"^{CB_END_TRAINING}$")
            ],
            FLASHCARD_EVAL: [
                CallbackQueryHandler(handle_self_evaluation, pattern=f"^{CB_EVAL_CORRECT}|{CB_EVAL_INCORRECT}$")
            ],
            AWAITING_VERB_ANSWER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_verb_answer)
            ],
            VERB_TRAINER_NEXT_ACTION: [
                CallbackQueryHandler(start_verb_trainer, pattern=f"^{CB_VERB_TRAINER_START}$"),
                CallbackQueryHandler(training_menu, pattern=f"^{CB_TRAIN_MENU}$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(end_training, pattern=f"^{CB_END_TRAINING}$"),
            CallbackQueryHandler(back_to_main_menu, pattern="^main_menu$"),
            CallbackQueryHandler(main_menu, pattern="^main_menu$")
        ],
        map_to_parent={
            ConversationHandler.END: TRAINING_MENU_STATE
        },
        **conv_defaults
    )

    # 5. Добавляем все обработчики в приложение
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    
    # --- НАЧАЛО ИЗМЕНЕНИЯ: Паттерны используют ':' вместо '_' ---
    # Обработчики словаря
    application.add_handler(CallbackQueryHandler(view_dictionary_page_handler, pattern=f"^({CB_DICT_VIEW}|{CB_DICT_DELETE_MODE}):"))
    application.add_handler(CallbackQueryHandler(confirm_delete_word, pattern=f"^{CB_DICT_CONFIRM_DELETE}:"))
    application.add_handler(CallbackQueryHandler(execute_delete_word, pattern=f"^{CB_DICT_EXECUTE_DELETE}:"))
    
    # Обработчики карточки слова
    application.add_handler(CallbackQueryHandler(add_word_to_dictionary, pattern=f"^{CB_ADD}:"))
    application.add_handler(CallbackQueryHandler(show_verb_conjugations, pattern=f"^{CB_SHOW_VERB}:"))
    application.add_handler(CallbackQueryHandler(view_word_card_handler, pattern=f"^{CB_VIEW_CARD}:"))
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
    
    # Добавляем ConversationHandler для тренировок
    application.add_handler(training_conv)
    
    # Обработчик текстовых сообщений (должен идти одним из последних)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # 6. Запускаем бота
    logger.info("Бот запускается...")
    application.run_polling()
    
    # Корректное завершение работы
    DB_WRITE_QUEUE.put(None)
    db_worker_thread.join()


if __name__ == "__main__":
    main()