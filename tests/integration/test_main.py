from main import build_application, main
from telegram.ext import Application
from unittest.mock import MagicMock, patch


def test_build_application(monkeypatch):
    """Test that the build_application function returns an Application object."""
    monkeypatch.setattr("main.BOT_TOKEN", "test_token")
    application = build_application()
    assert isinstance(application, Application)


def test_no_token(monkeypatch):
    """Test that the build_application function returns an Application object."""
    monkeypatch.setattr("main.BOT_TOKEN", None)
    with patch("main.sys.exit", new_callable=MagicMock) as sys_exit:
        main()
        sys_exit.assert_called_once_with("Токен не найден.")
