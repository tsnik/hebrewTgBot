import pytest
import asyncio
from httpx import AsyncClient
import respx
from telegram import Update
import threading
import time

from app.main import build_application
from tests.conftest import monkeypatch_session


@pytest.fixture(scope="module")
def running_app(monkeypatch_session):
    """Starts the bot and metrics server in a separate thread."""
    monkeypatch_session.setattr("app.main.BOT_TOKEN", "bot_token")
    application = build_application()
    from prometheus_client.exposition import MetricsHandler
    from http.server import HTTPServer

    class StoppableHTTPServer(HTTPServer):
        def run(self):
            self.serve_forever()

        def stop(self):
            self.shutdown()

    server = StoppableHTTPServer(("", 8000), MetricsHandler)

    server_thread = threading.Thread(target=server.run)
    server_thread.daemon = True
    server_thread.start()
    time.sleep(1)

    async def run_bot():
        await application.initialize()
        await application.start()
        await application.updater.start_polling()

    bot_thread = threading.Thread(target=lambda: asyncio.run(run_bot()))
    bot_thread.daemon = True
    bot_thread.start()

    yield application

    server.stop()
    server_thread.join(timeout=1)
    asyncio.run(application.updater.stop())
    asyncio.run(application.stop())
    asyncio.run(application.shutdown())
    bot_thread.join(timeout=1)


@pytest.mark.asyncio
async def test_metrics_endpoint(running_app):
    """Test that the /metrics endpoint is available."""
    async with AsyncClient() as client:
        response = await client.get("http://localhost:8000/metrics")
        assert response.status_code == 200
        assert "bot_messages_total" in response.text
        assert "bot_callbacks_total" in response.text


@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False)
async def test_message_counter(running_app):
    """Test that the message counter is incremented."""
    application = running_app
    respx.post("https://api.telegram.org/bot_token/getUpdates").respond(
        200, json={"ok": True, "result": []}
    )
    respx.post("https://api.telegram.org/bot_token/sendMessage").respond(
        200, json={"ok": True, "result": {}}
    )

    async with AsyncClient() as client:
        # Get initial metrics
        response = await client.get("http://localhost:8000/metrics")
        initial_messages = float(
            [
                line.split(" ")[1]
                for line in response.text.split("\n")
                if line.startswith("bot_messages_total")
            ][0]
        )

        # Simulate a message
        update = Update(
            1,
            message={
                "message_id": 1,
                "date": 1,
                "chat": {"id": 1, "type": "private"},
                "text": "hello",
            },
        )
        await application.process_update(update)

        # Get updated metrics
        response = await client.get("http://localhost:8000/metrics")
        updated_messages = float(
            [
                line.split(" ")[1]
                for line in response.text.split("\n")
                if line.startswith("bot_messages_total")
            ][0]
        )

        assert updated_messages == initial_messages + 1


@pytest.mark.asyncio
@respx.mock(assert_all_mocked=False)
async def test_callback_counter(running_app):
    """Test that the callback counter is incremented."""
    application = running_app
    respx.post("https://api.telegram.org/bot_token/getUpdates").respond(
        200, json={"ok": True, "result": []}
    )
    respx.post("https://api.telegram.org/bot_token/answerCallbackQuery").respond(
        200, json={"ok": True, "result": {}}
    )
    respx.post("https://api.telegram.org/bot_token/editMessageText").respond(
        200, json={"ok": True, "result": {}}
    )

    async with AsyncClient() as client:
        # Get initial metrics
        response = await client.get("http://localhost:8000/metrics")
        initial_callbacks = float(
            [
                line.split(" ")[1]
                for line in response.text.split("\n")
                if line.startswith("bot_callbacks_total")
            ][0]
        )

        # Simulate a callback
        update = Update(
            2,
            callback_query={
                "id": "1",
                "from": {"id": 1, "is_bot": False, "first_name": "test"},
                "message": {
                    "message_id": 1,
                    "date": 1,
                    "chat": {"id": 1, "type": "private"},
                    "text": "hello",
                },
                "chat_instance": "1",
                "data": "main_menu",
            },
        )
        await application.process_update(update)

        # Get updated metrics
        response = await client.get("http://localhost:8000/metrics")
        updated_callbacks = float(
            [
                line.split(" ")[1]
                for line in response.text.split("\n")
                if line.startswith("bot_callbacks_total")
            ][0]
        )

        assert updated_callbacks == initial_callbacks + 1
