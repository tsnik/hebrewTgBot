import pytest
from app.main import build_application
from telegram.ext import Application


def test_build_application(monkeypatch):
    """Test that the build_application function returns an Application object."""
    monkeypatch.setattr("app.main.BOT_TOKEN", "test_token")
    application = build_application()
    assert isinstance(application, Application)
