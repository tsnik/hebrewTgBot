# -*- coding: utf-8 -*-

import sys

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

from config import (
    BOT_TOKEN,
    logger,
    CONVERSATION_TIMEOUT_SECONDS,
    TRAINING_MENU_STATE,
    FLASHCARD_SHOW,
    FLASHCARD_EVAL,
    AWAITING_VERB_ANSWER,
    VERB_TRAINER_NEXT_ACTION,
    CB_DICT_VIEW,
    CB_DICT_DELETE_MODE,
    CB_DICT_CONFIRM_DELETE,
    CB_DICT_EXECUTE_DELETE,
    CB_ADD,
    CB_SHOW_VERB,
    CB_VIEW_CARD,
    CB_TRAIN_MENU,
    CB_TRAIN_HE_RU,
    CB_TRAIN_RU_HE,
    CB_VERB_TRAINER_START,
    CB_SHOW_ANSWER,
    CB_EVAL_CORRECT,
    CB_EVAL_INCORRECT,
    CB_END_TRAINING,
    CB_SEARCH_PEALIM,
    CB_SELECT_WORD,
    CB_SETTINGS_MENU,
    CB_TENSES_MENU,
    CB_TENSE_TOGGLE,
    CB_TOGGLE_TRAINING_MODE,
    CB_SHOW_ALL_VERB_FORMS,
)

# Импортируем обработчики
from handlers.common import start, main_menu, back_to_main_menu
from handlers.search import (
    handle_text_message,
    add_word_to_dictionary,
    show_verb_conjugations,
    view_word_card_handler,
    pealim_search_handler,
    select_word_handler,
    show_all_verb_forms_handler,
)
from handlers.dictionary import (
    view_dictionary_page_handler,
    confirm_delete_word,
    execute_delete_word,
)
from handlers.training import (
    training_menu,
    start_flashcard_training,
    show_answer,
    handle_self_evaluation,
    start_verb_trainer,
    check_verb_answer,
    end_training,
)

from prometheus_client import start_http_server

from handlers.settings import (
    settings_menu,
    toggle_tense,
    manage_tenses_menu,
    toggle_training_mode_handler,
)


def build_application() -> Application:
    """Строит и возвращает объект Application."""
    application = Application.builder().token(BOT_TOKEN).build()

    conv_defaults = {
        "per_user": True,
        "per_chat": True,
        "conversation_timeout": CONVERSATION_TIMEOUT_SECONDS,
    }

    training_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(training_menu, pattern=f"^{CB_TRAIN_MENU}$")
        ],
        states={
            TRAINING_MENU_STATE: [
                CallbackQueryHandler(training_menu, pattern=f"^{CB_TRAIN_MENU}$"),
                CallbackQueryHandler(
                    start_flashcard_training,
                    pattern=f"^({CB_TRAIN_HE_RU}|{CB_TRAIN_RU_HE})$",
                ),
                CallbackQueryHandler(
                    start_verb_trainer, pattern=f"^{CB_VERB_TRAINER_START}$"
                ),
                CallbackQueryHandler(back_to_main_menu, pattern="^main_menu$"),
            ],
            FLASHCARD_SHOW: [
                CallbackQueryHandler(show_answer, pattern=f"^{CB_SHOW_ANSWER}$"),
                CallbackQueryHandler(end_training, pattern=f"^{CB_END_TRAINING}$"),
            ],
            FLASHCARD_EVAL: [
                CallbackQueryHandler(
                    handle_self_evaluation,
                    pattern=f"^{CB_EVAL_CORRECT}|{CB_EVAL_INCORRECT}$",
                )
            ],
            AWAITING_VERB_ANSWER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_verb_answer)
            ],
            VERB_TRAINER_NEXT_ACTION: [
                CallbackQueryHandler(
                    start_verb_trainer, pattern=f"^{CB_VERB_TRAINER_START}$"
                ),
                CallbackQueryHandler(training_menu, pattern=f"^{CB_TRAIN_MENU}$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(end_training, pattern=f"^{CB_END_TRAINING}$"),
            CallbackQueryHandler(back_to_main_menu, pattern="^main_menu$"),
            CallbackQueryHandler(main_menu, pattern="^main_menu$"),
        ],
        map_to_parent={ConversationHandler.END: TRAINING_MENU_STATE},
        **conv_defaults,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))

    application.add_handler(
        CallbackQueryHandler(
            view_dictionary_page_handler,
            pattern=f"^({CB_DICT_VIEW}|{CB_DICT_DELETE_MODE}):",
        )
    )
    application.add_handler(
        CallbackQueryHandler(confirm_delete_word, pattern=f"^{CB_DICT_CONFIRM_DELETE}:")
    )
    application.add_handler(
        CallbackQueryHandler(execute_delete_word, pattern=f"^{CB_DICT_EXECUTE_DELETE}:")
    )

    application.add_handler(
        CallbackQueryHandler(add_word_to_dictionary, pattern=f"^{CB_ADD}:")
    )
    application.add_handler(
        CallbackQueryHandler(show_verb_conjugations, pattern=f"^{CB_SHOW_VERB}:")
    )
    application.add_handler(
        CallbackQueryHandler(view_word_card_handler, pattern=f"^{CB_VIEW_CARD}:")
    )

    application.add_handler(
        CallbackQueryHandler(
            show_all_verb_forms_handler, pattern=f"^{CB_SHOW_ALL_VERB_FORMS}:"
        )
    )

    application.add_handler(
        CallbackQueryHandler(pealim_search_handler, pattern=f"^{CB_SEARCH_PEALIM}:")
    )

    application.add_handler(
        CallbackQueryHandler(select_word_handler, pattern=f"^{CB_SELECT_WORD}:")
    )

    # Обработчики настроек
    application.add_handler(
        CallbackQueryHandler(settings_menu, pattern=f"^{CB_SETTINGS_MENU}$")
    )
    application.add_handler(
        CallbackQueryHandler(manage_tenses_menu, pattern=f"^{CB_TENSES_MENU}$")
    )
    application.add_handler(
        CallbackQueryHandler(toggle_tense, pattern=f"^{CB_TENSE_TOGGLE}:")
    )

    application.add_handler(
        CallbackQueryHandler(
            toggle_training_mode_handler, pattern=f"^{CB_TOGGLE_TRAINING_MODE}$"
        )
    )

    application.add_handler(training_conv)

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
    )
    return application


def main() -> None:
    """Основная функция для запуска бота."""
    if BOT_TOKEN is None:
        logger.critical(
            "Токен бота не найден. Укажите TELEGRAM_BOT_TOKEN в .env файле."
        )
        sys.exit("Токен не найден.")
        return

    application = build_application()
    logger.info("Бот запускается...")
    application.run_polling()


if __name__ == "__main__":
    from prometheus_client import REGISTRY

    start_http_server(8000, registry=REGISTRY)
    main()
