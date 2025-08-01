from dal.repositories import UserSettingsRepository
from dal.models import UserSettings, Tense


def test_initialize_and_get_user_settings(
    user_settings_repo: UserSettingsRepository, unique_user_id: int
):
    """
    Тест:
    1. Настройки по умолчанию корректно создаются для нового пользователя.
    2. Настройки корректно извлекаются в виде Pydantic модели UserSettings.
    """
    user_id = unique_user_id

    # 1. Вызываем инициализацию
    with user_settings_repo.connection:
        user_settings_repo.initialize_tense_settings(user_id)

    # 2. Получаем модель с настройками
    settings_model = user_settings_repo.get_user_settings(user_id)

    # 3. Проверяем саму модель
    assert isinstance(settings_model, UserSettings)
    assert settings_model.user_id == user_id
    assert len(settings_model.tense_settings) == 4

    # 4. Проверяем удобные методы модели
    active_tenses = settings_model.get_active_tenses()
    settings_dict = settings_model.get_settings_as_dict()

    assert set(active_tenses) == {"perf", "ap", "impf", "imp"}
    assert settings_dict["perf"] is True
    assert settings_dict["ap"] is True
    assert settings_dict["impf"] is True
    assert settings_dict["imp"] is True


def test_toggle_tense_setting(
    user_settings_repo: UserSettingsRepository, unique_user_id: int
):
    """Тест: переключение статуса времени работает корректно с использованием Enum."""
    user_id = unique_user_id
    with user_settings_repo.connection:
        user_settings_repo.initialize_tense_settings(user_id)

    # 1. Проверяем начальное состояние (imp - активно)
    initial_model = user_settings_repo.get_user_settings(user_id)
    assert initial_model.get_settings_as_dict()["imp"] is True

    # 2. Переключаем 'imp', передавая Enum
    with user_settings_repo.connection:
        user_settings_repo.toggle_tense_setting(user_id, Tense.IMPERATIVE)

    # 3. Проверяем, что 'imp' стало неактивным
    toggled_model_1 = user_settings_repo.get_user_settings(user_id)
    assert toggled_model_1.get_settings_as_dict()["imp"] is False

    # 4. Переключаем 'imp' еще раз
    with user_settings_repo.connection:
        user_settings_repo.toggle_tense_setting(user_id, Tense.IMPERATIVE)

    # 5. Проверяем, что 'imp' снова стало активным
    toggled_model_2 = user_settings_repo.get_user_settings(user_id)
    assert toggled_model_2.get_settings_as_dict()["imp"] is True
