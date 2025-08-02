import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from handlers.settings import (
    settings_menu,
    manage_tenses_menu,
    toggle_tense,
    toggle_training_mode_handler,
)
from dal.models import UserSettings, UserTenseSetting, Tense
from config import (
    CB_TENSE_TOGGLE,
    CB_TOGGLE_TRAINING_MODE,
)


@pytest.mark.asyncio
async def test_settings_menu(monkeypatch):
    """Тест: главное меню настроек корректно отображает все элементы,
    включая динамический статус режима тренировки."""
    update = AsyncMock()
    update.callback_query.from_user.id = 123
    context = MagicMock()

    # Моделируем два состояния настроек для проверки
    mock_settings_off = UserSettings(user_id=123, use_grammatical_forms=False)
    mock_settings_on = UserSettings(user_id=123, use_grammatical_forms=True)

    descriptive_text = "В продвинутом режиме тренировки"  # Текст для проверки

    with patch("handlers.settings.UnitOfWork") as mock_uow_class:
        mock_uow = mock_uow_class.return_value.__enter__.return_value

        # --- Сценарий 1: Режим тренировки форм ВЫКЛЮЧЕН ---
        mock_uow.user_settings.get_user_settings.return_value = mock_settings_off
        await settings_menu(update, context)

        update.callback_query.edit_message_text.assert_called_once()
        call_kwargs_off = update.callback_query.edit_message_text.call_args.kwargs
        keyboard_off = call_kwargs_off["reply_markup"].inline_keyboard

        assert "Настройки" in call_kwargs_off["text"]
        assert descriptive_text in call_kwargs_off["text"]
        assert len(keyboard_off) == 3  # Проверяем, что кнопок теперь три
        assert "🕰️ Мои времена глаголов" in keyboard_off[0][0].text
        assert "🔄 Продвинутый режим: ⬜️ Выкл" in keyboard_off[1][0].text
        assert "⬅️ В главное меню" in keyboard_off[2][0].text

        update.callback_query.edit_message_text.reset_mock()  # Сбрасываем мок для следующей проверки

        # --- Сценарий 2: Режим тренировки форм ВКЛЮЧЕН ---
        mock_uow.user_settings.get_user_settings.return_value = mock_settings_on
        await settings_menu(update, context)

        update.callback_query.edit_message_text.assert_called_once()
        call_kwargs_on = update.callback_query.edit_message_text.call_args.kwargs
        keyboard_on = call_kwargs_on["reply_markup"].inline_keyboard
        assert "🔄 Продвинутый режим: ✅ Вкл" in keyboard_on[1][0].text


@pytest.mark.asyncio
async def test_toggle_training_mode_handler():
    """Тест: нажатие на кнопку переключения режима вызывает обновление в БД и перерисовку меню."""
    update = AsyncMock()
    update.callback_query.from_user.id = 123
    update.callback_query.data = CB_TOGGLE_TRAINING_MODE
    context = MagicMock()

    with patch("handlers.settings.UnitOfWork") as mock_uow_class:
        mock_uow = mock_uow_class.return_value.__enter__.return_value

        # Мокаем `settings_menu` для проверки, что она была вызвана для обновления
        with patch(
            "handlers.settings.settings_menu", new_callable=AsyncMock
        ) as mock_settings_menu:
            await toggle_training_mode_handler(update, context)

            # Проверяем, что была вызвана логика переключения в БД
            mock_uow.user_settings.toggle_training_mode.assert_called_once_with(123)
            mock_uow.commit.assert_called_once()

            # Проверяем, что меню было перерисовано
            mock_settings_menu.assert_called_once()


@pytest.mark.asyncio
async def test_manage_tenses_menu_initialization():
    """Тест: при первом входе в меню настроек, они инициализируются."""
    update = AsyncMock()
    update.callback_query.from_user.id = 123
    context = MagicMock()

    empty_settings_model = UserSettings(user_id=123)

    # Модель с настройками по умолчанию
    default_settings_model = UserSettings(
        user_id=123,
        tense_settings=[
            UserTenseSetting(user_id=123, tense=Tense.PAST, is_active=True),
            UserTenseSetting(user_id=123, tense=Tense.PRESENT, is_active=True),
            UserTenseSetting(user_id=123, tense=Tense.FUTURE, is_active=True),
            UserTenseSetting(user_id=123, tense=Tense.IMPERATIVE, is_active=False),
        ],
    )

    with patch("handlers.settings.UnitOfWork") as mock_uow_class:
        mock_uow = mock_uow_class.return_value.__enter__.return_value
        # Сначала настроек нет, потом они появляются после инициализации
        mock_uow.user_settings.get_user_settings.side_effect = [
            empty_settings_model,
            default_settings_model,
        ]

        await manage_tenses_menu(update, context)

        # Проверяем, что была вызвана инициализация
        mock_uow.user_settings.initialize_tense_settings.assert_called_once_with(123)
        mock_uow.commit.assert_called_once()

        # Проверяем, что меню было отрисовано
        update.callback_query.edit_message_text.assert_called_once()
        call_kwargs = update.callback_query.edit_message_text.call_args.kwargs
        keyboard = call_kwargs["reply_markup"].inline_keyboard
        assert "✅ Прошедшее" in keyboard[0][0].text
        assert "⬜️ Повелительное" in keyboard[3][0].text


@pytest.mark.asyncio
async def test_toggle_tense():
    """Тест: нажатие на кнопку времени вызывает обновление в БД и перерисовку меню."""
    update = AsyncMock()
    update.callback_query.from_user.id = 123
    update.callback_query.data = f"{CB_TENSE_TOGGLE}:imp"  # Переключаем повелительное
    context = MagicMock()

    with patch("handlers.settings.UnitOfWork") as mock_uow_class:
        mock_uow = mock_uow_class.return_value.__enter__.return_value

        # Мокаем `manage_tenses_menu` для проверки, что она была вызвана для обновления
        with patch(
            "handlers.settings.manage_tenses_menu", new_callable=AsyncMock
        ) as mock_manage_menu:
            await toggle_tense(update, context)

            # Проверяем, что была вызвана логика переключения в БД
            mock_uow.user_settings.toggle_tense_setting.assert_called_once_with(
                123, "imp"
            )

            # Проверяем, что меню было перерисовано
            mock_manage_menu.assert_called_once()
