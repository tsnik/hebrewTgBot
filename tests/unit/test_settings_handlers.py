import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from handlers.settings import settings_menu, manage_tenses_menu, toggle_tense
from dal.models import UserSettings, UserTenseSetting, Tense
from config import CB_TENSES_MENU, CB_TENSE_TOGGLE


@pytest.mark.asyncio
async def test_settings_menu():
    """Тест: главное меню настроек отображается корректно."""
    update = AsyncMock()
    context = MagicMock()

    await settings_menu(update, context)

    update.callback_query.answer.assert_called_once()
    update.callback_query.edit_message_text.assert_called_once()

    call_kwargs = update.callback_query.edit_message_text.call_args.kwargs
    assert "Настройки" in call_kwargs["text"]

    keyboard = call_kwargs["reply_markup"].inline_keyboard
    assert len(keyboard) == 2
    assert "Мои времена глаголов" in keyboard[0][0].text
    assert keyboard[0][0].callback_data == CB_TENSES_MENU


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
            mock_uow.commit.assert_called_once()

            # Проверяем, что меню было перерисовано
            mock_manage_menu.assert_called_once()
